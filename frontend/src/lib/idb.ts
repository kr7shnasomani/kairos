// IndexedDB write queue — stores failed POSTs for offline replay.
// Only called client-side; no-ops when indexedDB is unavailable (SSR).
import { getToken, refreshAccessToken, tokenUserId, API_BASE, QUEUE_DB as DB } from "./api";

const STORE = "write-queue";

interface QueuedWrite {
  id?: number;
  url: string;
  method: string;
  body: string;
  /** `sub` of the user who queued it. A write is only replayed for that same user. */
  user?: string;
}

function open(): Promise<IDBDatabase> {
  return new Promise((res, rej) => {
    const r = indexedDB.open(DB, 1);
    r.onupgradeneeded = () =>
      r.result.createObjectStore(STORE, { keyPath: "id", autoIncrement: true });
    r.onsuccess = () => res(r.result);
    r.onerror = () => rej(r.error);
  });
}

export async function enqueueWrite(path: string, method: string, body: unknown): Promise<void> {
  if (typeof indexedDB === "undefined") return;
  const db = await open();
  try {
    await new Promise<void>((res, rej) => {
      const tx = db.transaction(STORE, "readwrite");
      tx.objectStore(STORE).add({
        url: `${API_BASE}${path}`,
        method,
        body: JSON.stringify(body),
        user: tokenUserId(getToken()),
      });
      tx.oncomplete = () => res();
      tx.onerror = () => rej(tx.error);
    });
  } finally {
    db.close();
  }
}

export async function getQueueLength(): Promise<number> {
  if (typeof indexedDB === "undefined") return 0;
  const db = await open();
  try {
    return await new Promise<number>((res, rej) => {
      const r = db.transaction(STORE, "readonly").objectStore(STORE).count();
      r.onsuccess = () => res(r.result);
      r.onerror = () => rej(r.error);
    });
  } finally {
    db.close();
  }
}

// Bounded so one hung endpoint can't stall the whole sequential replay loop.
const REPLAY_TIMEOUT_MS = 8000;

export async function flushQueue(): Promise<{ replayed: number; failed: number }> {
  if (typeof indexedDB === "undefined") return { replayed: 0, failed: 0 };
  const db = await open();
  try {
    const items = await new Promise<QueuedWrite[]>((res, rej) => {
      const r = db.transaction(STORE, "readonly").objectStore(STORE).getAll();
      r.onsuccess = () => res(r.result as QueuedWrite[]);
      r.onerror = () => rej(r.error);
    });

    const remove = (id: number) =>
      new Promise<void>((res2) => {
        const tx = db.transaction(STORE, "readwrite");
        tx.objectStore(STORE).delete(id);
        tx.oncomplete = () => res2();
      });

    const replay = (item: QueuedWrite) => {
      const token = getToken();
      return fetch(item.url, {
        method: item.method,
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: item.body,
        signal: AbortSignal.timeout(REPLAY_TIMEOUT_MS),
      });
    };

    let replayed = 0;
    let failed = 0;
    let refreshTried = false;
    // Nobody signed in: keep everything for whoever signs in next (their own entries only).
    if (!getToken()) return { replayed, failed: items.length };
    const me = tokenUserId(getToken());

    for (const item of items) {
      // Queued by someone else (or by a build that recorded no user): replaying it would file it
      // under the current user, so it is dropped, never sent.
      if ((item.user ?? null) !== me) {
        await remove(item.id!);
        continue;
      }
      try {
        let r = await replay(item);
        // A token that expired while offline 401s every item — refresh once per flush.
        if (r.status === 401 && !refreshTried) {
          refreshTried = true;
          if (await refreshAccessToken()) r = await replay(item);
        }
        if (r.ok || r.status === 409) {
          await remove(item.id!);
          replayed++;
        } else if (r.status >= 400 && r.status < 500 && r.status !== 401) {
          // Client error: replaying the same payload can never succeed. Drop it so
          // one bad write can't poison the queue and inflate the badge forever.
          await remove(item.id!);
          failed++;
        } else {
          failed++; // network/5xx/unrefreshed 401: keep for the next flush
        }
      } catch {
        failed++;
      }
    }
    return { replayed, failed };
  } finally {
    db.close();
  }
}

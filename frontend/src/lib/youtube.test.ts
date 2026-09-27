import { describe, expect, it } from "vitest";
import { youTubeId } from "./youtube";

// The landing's demo player turns on by pasting a URL into DEMO_YOUTUBE_URL, so
// this parser is the switch. A silent null means the section never appears.
describe("youTubeId", () => {
  it("reads every shape a YouTube link is pasted in", () => {
    for (const url of [
      "https://www.youtube.com/watch?v=aqz-KE-bpKQ",
      "https://www.youtube.com/watch?list=PL1&v=aqz-KE-bpKQ&t=30s",
      "https://youtu.be/aqz-KE-bpKQ?t=12",
      "https://www.youtube.com/embed/aqz-KE-bpKQ",
      "https://www.youtube.com/shorts/aqz-KE-bpKQ",
    ]) {
      expect(youTubeId(url)).toBe("aqz-KE-bpKQ");
    }
  });

  it("returns null for anything that is not a YouTube video", () => {
    expect(youTubeId("")).toBeNull();
    expect(youTubeId("https://drive.google.com/file/d/18ZO95MckNtESg/view")).toBeNull();
    expect(youTubeId("https://vimeo.com/123456789")).toBeNull();
  });
});

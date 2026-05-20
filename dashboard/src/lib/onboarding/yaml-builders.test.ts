/**
 * @packageDocumentation
 *
 * Behavioral tests for {@link setAdzunaEnabledInYaml}.
 *
 * @remarks
 * The helper performs a surgical edit to `companies.yaml` so the
 * onboarding wizard can flip Adzuna on without rewriting the rest of
 * the user's config. These tests lock in that contract:
 *
 * - Flipping an existing `enabled:` line in place.
 * - Appending a minimal block when the file has no `adzuna:` section.
 * - Idempotency on repeat invocations.
 * - Preservation of comments and adjacent blocks byte-for-byte.
 */

import { describe, expect, it } from "vitest";

import {
  buildKeylessBoardsBlocks,
  setAdzunaEnabledInYaml,
} from "@/lib/onboarding/yaml-builders";

describe("setAdzunaEnabledInYaml — flipping an existing block", () => {
  it("flips enabled: false to enabled: true in place", () => {
    // Arrange
    const yaml = ["adzuna:", "  enabled: false", '  country: "us"', ""].join("\n");

    // Act
    const result = setAdzunaEnabledInYaml(yaml, true);

    // Assert
    expect(result).toContain("  enabled: true");
    expect(result).not.toContain("  enabled: false");
    expect(result).toContain('  country: "us"');
  });

  it("flips enabled: true to enabled: false in place", () => {
    // Arrange
    const yaml = ["adzuna:", "  enabled: true", '  country: "us"'].join("\n");

    // Act
    const result = setAdzunaEnabledInYaml(yaml, false);

    // Assert
    expect(result).toContain("  enabled: false");
    expect(result).not.toContain("  enabled: true");
  });

  it("returns the YAML untouched when the toggle already matches", () => {
    // Arrange
    const yaml = ["adzuna:", "  enabled: true", '  country: "us"'].join("\n");

    // Act
    const result = setAdzunaEnabledInYaml(yaml, true);

    // Assert: only the enabled line is rewritten verbatim, so byte-for-byte equality holds.
    expect(result).toBe(yaml);
  });
});

describe("setAdzunaEnabledInYaml — appending when block is missing", () => {
  it("appends a minimal adzuna block when none exists", () => {
    // Arrange
    const yaml = ["greenhouse_companies: {}", ""].join("\n");

    // Act
    const result = setAdzunaEnabledInYaml(yaml, true);

    // Assert
    expect(result).toContain("adzuna:\n  enabled: true");
    expect(result).toContain('  country: "us"');
    expect(result).toContain("  results_wanted: 50");
    // Pre-existing config is left untouched.
    expect(result).toContain("greenhouse_companies: {}");
  });

  it("does not duplicate the adzuna block on a second invocation", () => {
    // Arrange
    const yaml = "greenhouse_companies: {}\n";

    // Act
    const firstPass = setAdzunaEnabledInYaml(yaml, true);
    const secondPass = setAdzunaEnabledInYaml(firstPass, true);

    // Assert
    const headerMatches = secondPass.match(/^adzuna:\s*$/gm) ?? [];
    expect(headerMatches).toHaveLength(1);
    const enabledMatches = secondPass.match(/^\s+enabled:\s*(true|false)\s*$/gm) ?? [];
    expect(enabledMatches).toHaveLength(1);
  });

  it("flips the value on a subsequent invocation rather than re-appending", () => {
    // Arrange
    const seed = setAdzunaEnabledInYaml("greenhouse_companies: {}\n", true);

    // Act
    const flipped = setAdzunaEnabledInYaml(seed, false);

    // Assert
    expect(flipped).toContain("enabled: false");
    expect(flipped).not.toContain("enabled: true");
    const headerMatches = flipped.match(/^adzuna:\s*$/gm) ?? [];
    expect(headerMatches).toHaveLength(1);
  });

  it("inserts an enabled key when the block exists but lacks one", () => {
    // Arrange
    const yaml = ["adzuna:", '  country: "us"', "  results_wanted: 25"].join("\n");

    // Act
    const result = setAdzunaEnabledInYaml(yaml, true);

    // Assert: enabled line lands right after the header, before sibling fields.
    const lines = result.split("\n");
    const headerIdx = lines.findIndex((line) => /^adzuna:\s*$/.test(line));
    expect(headerIdx).toBeGreaterThanOrEqual(0);
    expect(lines[headerIdx + 1]).toBe("  enabled: true");
    expect(result).toContain('  country: "us"');
    expect(result).toContain("  results_wanted: 25");
  });
});

describe("setAdzunaEnabledInYaml — preserving surrounding content", () => {
  it("preserves comments inside the adzuna block while flipping the value", () => {
    // Arrange
    const yaml = [
      "adzuna:",
      "  # API key required from developer.adzuna.com",
      "  enabled: false",
      '  country: "us"',
    ].join("\n");

    // Act
    const result = setAdzunaEnabledInYaml(yaml, true);

    // Assert
    expect(result).toContain("  # API key required from developer.adzuna.com");
    expect(result).toContain("  enabled: true");
  });

  it("leaves an adjacent lever_companies block byte-for-byte unchanged", () => {
    // Arrange
    const adzunaBefore = ["adzuna:", "  enabled: false", '  country: "us"'].join("\n");
    const leverBlock = [
      "",
      "lever_companies:",
      "  ExampleCo:",
      '    lever_id: "exampleco"',
      "    enabled: true",
    ].join("\n");
    const yaml = adzunaBefore + leverBlock + "\n";

    // Act
    const result = setAdzunaEnabledInYaml(yaml, true);

    // Assert: the lever block survives verbatim, only the enabled line in the
    // adzuna block changes.
    expect(result).toContain(leverBlock);
    expect(result).toContain("  enabled: true");
  });

  it("does not cross out of the adzuna block when flipping enabled", () => {
    // Arrange: a sibling top-level block also carries an enabled: false line that
    // must NOT be touched by the Adzuna toggle.
    const yaml = [
      "adzuna:",
      "  enabled: false",
      "",
      "themuse:",
      "  enabled: false",
    ].join("\n");

    // Act
    const result = setAdzunaEnabledInYaml(yaml, true);

    // Assert
    const lines = result.split("\n");
    const adzunaHeaderIdx = lines.findIndex((line) => /^adzuna:\s*$/.test(line));
    const themuseHeaderIdx = lines.findIndex((line) => /^themuse:\s*$/.test(line));
    expect(lines[adzunaHeaderIdx + 1]).toBe("  enabled: true");
    // The themuse enabled line stays false — proves the loop terminated at the
    // top-level boundary instead of mutating the wrong block.
    expect(lines[themuseHeaderIdx + 1]).toBe("  enabled: false");
  });
});

describe("buildKeylessBoardsBlocks", () => {
  it("emits indeed/linkedin/glassdoor under job_boards plus a linkedin scraper block", () => {
    // Arrange / Act
    const result = buildKeylessBoardsBlocks(["software engineer intern"]);

    // Assert: each keyless source appears with enabled: true
    expect(result).toMatch(/^job_boards:/m);
    expect(result).toMatch(/^ {2}indeed:\n {4}enabled: true/m);
    expect(result).toMatch(/^ {2}linkedin:\n {4}enabled: true/m);
    expect(result).toMatch(/^ {2}glassdoor:\n {4}enabled: true/m);
    expect(result).toMatch(/^linkedin:\n {2}enabled: true/m);
    expect(result).toContain('- "software engineer intern"');
  });

  it("falls back to a generic intern query when given no search terms", () => {
    // Arrange / Act
    const result = buildKeylessBoardsBlocks([]);

    // Assert: at least one search term is present so each board still queries
    expect(result).toContain('- "software engineer intern"');
  });

  it("escapes embedded double quotes in user-provided search terms", () => {
    // Arrange / Act
    const result = buildKeylessBoardsBlocks(['weird "quoted" role']);

    // Assert: double quotes get backslash-escaped inside the YAML scalar
    expect(result).toContain('- "weird \\"quoted\\" role"');
  });
});

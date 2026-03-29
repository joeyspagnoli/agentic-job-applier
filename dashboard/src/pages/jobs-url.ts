const ALLOWED_EXTERNAL_PROTOCOLS = new Set(["http:", "https:"]);

/**
 * Validate and normalize one job-posting URL for safe anchor rendering.
 *
 * @param rawUrl - Raw URL value from backend payload.
 * @returns Absolute URL string when protocol is allowed, else `null`.
 */
export function toSafeJobPostingUrl(rawUrl: string): string | null {
  if (rawUrl.trim() === "") {
    return null;
  }

  try {
    const parsedUrl = new URL(rawUrl);
    if (!ALLOWED_EXTERNAL_PROTOCOLS.has(parsedUrl.protocol)) {
      return null;
    }
    return parsedUrl.toString();
  } catch {
    return null;
  }
}

// @vitest-environment jsdom
/**
 * @packageDocumentation
 *
 * Integration tests for the {@link OnboardingPage} `handleFinish` flow.
 *
 * @remarks
 * These tests render the full wizard, drive it with React Testing Library,
 * and assert the two behaviors that unit tests on extracted helpers cannot
 * cover:
 *
 * - **Bug 2 — navigation order:** `navigate("/")` must fire only after
 *   `queryClient.refetchQueries` resolves so that {@link OnboardingGate}
 *   sees `is_complete: true` and does not bounce the user back to step 1.
 * - **Bug 4 — delayed redirect on watchlist warning:** when the watchlist
 *   step produced unverified or network-failed companies, the wizard must
 *   render a warning, wait `WATCHLIST_WARNING_REDIRECT_DELAY_MS` (3500 ms),
 *   and only then navigate.
 *
 * The tests stub every API client call and the `useNavigate` hook so the
 * wizard never reaches the network. `globalThis.fetch` is also stubbed so
 * Greenhouse slug validation is fully controllable from each test.
 */

import "@testing-library/jest-dom/vitest";

import type { JSX } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

const navigateMock = vi.fn();

vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
  return {
    ...actual,
    useNavigate: (): typeof navigateMock => navigateMock,
  };
});

vi.mock("@/lib/api/client", () => ({
  updateProfileStructured: vi.fn().mockResolvedValue(undefined),
  uploadResumeTex: vi.fn().mockResolvedValue(undefined),
  updateFiltersYaml: vi.fn().mockResolvedValue(undefined),
  fetchSourcesSettings: vi.fn().mockResolvedValue({ yaml_text: "greenhouse_companies:\n" }),
  updateSourcesYaml: vi.fn().mockResolvedValue(undefined),
}));

import { OnboardingPage } from "@/pages/OnboardingPage";

/**
 * Time the wizard waits before redirecting after rendering a watchlist
 * warning. Must stay in lockstep with `WATCHLIST_WARNING_REDIRECT_DELAY_MS`
 * inside `OnboardingPage.tsx` — both numbers exist for the same reason.
 */
const WATCHLIST_WARNING_REDIRECT_DELAY_MS = 3500;

/**
 * Build a `QueryClient` configured to fail fast in tests — no retries, no
 * refetch on mount, no background polling.
 *
 * @returns A fresh `QueryClient` for the test under construction.
 */
function buildTestQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, refetchOnWindowFocus: false },
      mutations: { retry: false },
    },
  });
}

/**
 * Render `OnboardingPage` inside a fresh `QueryClient` and `MemoryRouter`.
 *
 * @param queryClient - The query client to inject; usually returned by
 *   {@link buildTestQueryClient}.
 * @returns The query client (for spying on `refetchQueries`).
 */
function renderOnboarding(queryClient: QueryClient): QueryClient {
  function Wrapper(): JSX.Element {
    return (
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <OnboardingPage />
        </MemoryRouter>
      </QueryClientProvider>
    );
  }
  render(<Wrapper />);
  return queryClient;
}

/**
 * Drive the wizard from the initial step through to the final
 * "Finish Setup" button by filling required fields and clicking
 * "Continue" / "Skip" as appropriate.
 *
 * @param user - The `userEvent` instance bound to the rendered tree.
 */
async function advanceWizardToFinishStep(user: ReturnType<typeof userEvent.setup>): Promise<void> {
  const fullNameField = screen.getByPlaceholderText("Jane Doe");
  await user.type(fullNameField, "Jane Tester");

  const emailField = screen.getByPlaceholderText("jane@example.com");
  await user.type(emailField, "jane@example.com");

  await user.click(screen.getByRole("button", { name: "Continue" }));

  const targetRolesField = await screen.findByPlaceholderText(/Software Engineer/);
  await user.type(targetRolesField, "Software Engineer");

  await user.click(screen.getByRole("button", { name: "Continue" }));

  // Steps 3-5 (Resume, Filters, Provider) are all skippable.
  for (let stepIndex = 0; stepIndex < 3; stepIndex += 1) {
    const skipButton = await screen.findByRole("button", { name: "Skip" });
    await user.click(skipButton);
  }

  // Step 6 (Apply Preferences) gates Continue until eligibility answers
  // are non-"unknown". Pick the unambiguous defaults so the helper can
  // advance to the watchlist step the test cares about.
  const workAuthSelect = await screen.findByLabelText(/Authorized to work in the U\.S\./);
  await user.selectOptions(workAuthSelect, "yes");
  const sponsorshipSelect = await screen.findByLabelText(/Requires sponsorship/);
  await user.selectOptions(sponsorshipSelect, "no");
  await user.click(screen.getByRole("button", { name: "Continue" }));
}

afterEach(() => {
  vi.useRealTimers();
  vi.clearAllMocks();
  cleanup();
});

describe("OnboardingPage handleFinish navigation order (Bug 2)", () => {
  beforeEach(() => {
    navigateMock.mockReset();
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("", { status: 200 }));
  });

  it("waits for refetchQueries to resolve before calling navigate", async () => {
    // Arrange — a deferred refetchQueries that we can release on demand.
    let releaseRefetch: () => void = () => undefined;
    const refetchPromise = new Promise<void>((resolve) => {
      releaseRefetch = resolve;
    });

    const queryClient = buildTestQueryClient();
    const refetchSpy = vi.spyOn(queryClient, "refetchQueries").mockReturnValue(refetchPromise);

    renderOnboarding(queryClient);
    const user = userEvent.setup();

    await advanceWizardToFinishStep(user);

    // Act — click Finish; refetchQueries is still pending.
    await user.click(screen.getByRole("button", { name: "Finish Setup" }));

    // Assert — the wizard is awaiting our deferred refetch, so navigate
    // must NOT have fired yet even though every other API call resolved.
    await waitFor(() => {
      expect(refetchSpy).toHaveBeenCalledOnce();
    });
    expect(navigateMock).not.toHaveBeenCalled();

    // Release the refetch and assert navigate now fires with "/".
    releaseRefetch();
    await waitFor(() => {
      expect(navigateMock).toHaveBeenCalledWith("/");
    });
  });
});

describe("OnboardingPage handleFinish watchlist warning (Bug 4)", () => {
  beforeEach(() => {
    navigateMock.mockReset();
  });

  it("renders a warning and delays navigate by 3500 ms when a slug is unverified", async () => {
    // Arrange — every Greenhouse probe returns 404.
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("", { status: 404 }));

    const queryClient = buildTestQueryClient();
    renderOnboarding(queryClient);
    const user = userEvent.setup();

    // Drive the wizard with real timers (userEvent + React Query don't
    // play nicely with fake timers during typing/animation).
    await advanceWizardToFinishStep(user);

    // Step 6: type one company so the unverified warning path triggers.
    const watchlistField = await screen.findByPlaceholderText(/Stripe/);
    await user.type(watchlistField, "Bogus Inc");

    // Act — click Finish under real timers so handleFinish's microtask
    // chain (validateGreenhouseSlug, refetchQueries, setState for the
    // warning) can progress without us needing to advance anything.
    await user.click(screen.getByRole("button", { name: "Finish Setup" }));

    // Assert — warning text appears under real timers.
    await waitFor(() => {
      expect(
        screen.getByText(/Could not verify Greenhouse IDs for: Bogus Inc/),
      ).toBeInTheDocument();
    });
    expect(navigateMock).not.toHaveBeenCalled();

    // The redirect uses setTimeout(navigate, 3500). Wait the real delay
    // plus a small buffer — short enough to keep the suite fast, long
    // enough to be deterministic. Vitest's default 5s test timeout is
    // overridden below to accommodate this wait.
    await waitFor(
      () => {
        expect(navigateMock).toHaveBeenCalledWith("/");
      },
      { timeout: WATCHLIST_WARNING_REDIRECT_DELAY_MS + 1500 },
    );
    expect(navigateMock).toHaveBeenCalledOnce();
  }, 10000);
});

describe("OnboardingPage watchlist banners — dismissible UI", () => {
  beforeEach(() => {
    navigateMock.mockReset();
  });

  it("removes the unverified-warning banner from the DOM when ✕ is clicked", async () => {
    // Arrange — every Greenhouse probe returns 404 so the unverified banner
    // appears for the typed company.
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("", { status: 404 }));

    const queryClient = buildTestQueryClient();
    renderOnboarding(queryClient);
    const user = userEvent.setup();

    await advanceWizardToFinishStep(user);

    const watchlistField = await screen.findByPlaceholderText(/Stripe/);
    await user.type(watchlistField, "Bogus Inc");

    await user.click(screen.getByRole("button", { name: "Finish Setup" }));

    // The unverified banner appears.
    await waitFor(() => {
      expect(
        screen.getByText(/Could not verify Greenhouse IDs for: Bogus Inc/),
      ).toBeInTheDocument();
    });

    // Act — click the dismiss button on the warning banner.
    const dismissButtons = screen.getAllByRole("button", { name: "Dismiss" });
    expect(dismissButtons.length).toBeGreaterThanOrEqual(1);
    await user.click(dismissButtons[0]!);

    // Assert — the banner text is gone from the DOM.
    expect(
      screen.queryByText(/Could not verify Greenhouse IDs for: Bogus Inc/),
    ).not.toBeInTheDocument();
  }, 10000);

  it("renders both banners independently when the watchlist contains both an unknown company and one confirmed absent from Greenhouse", async () => {
    // Arrange — "NVIDIA" hits the bundled lookup table (null → not_on_greenhouse,
    // no fetch call). "Bogus Inc" is unknown and every probe 404s, landing in
    // unverified. Both banners must render.
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("", { status: 404 }));

    const queryClient = buildTestQueryClient();
    renderOnboarding(queryClient);
    const user = userEvent.setup();

    await advanceWizardToFinishStep(user);

    const watchlistField = await screen.findByPlaceholderText(/Stripe/);
    await user.type(watchlistField, "NVIDIA{enter}Bogus Inc");

    await user.click(screen.getByRole("button", { name: "Finish Setup" }));

    // Both banners visible.
    await waitFor(() => {
      expect(
        screen.getByText(/Could not verify Greenhouse IDs for: Bogus Inc/),
      ).toBeInTheDocument();
    });
    expect(screen.getByText(/NVIDIA don't appear to use Greenhouse/)).toBeInTheDocument();

    // Two dismiss buttons must coexist — one per banner.
    expect(screen.getAllByRole("button", { name: "Dismiss" })).toHaveLength(2);
  }, 10000);
});

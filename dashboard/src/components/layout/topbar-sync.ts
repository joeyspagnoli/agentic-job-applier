/**
 * Determine whether a query should be refreshed by the global sync action.
 *
 * @param rootQueryKey - First segment of a React Query key.
 * @returns `true` when the query should be invalidated.
 */
export function shouldInvalidateOnSync(rootQueryKey: unknown): boolean {
  return rootQueryKey !== "settings";
}

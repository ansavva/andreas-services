import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  getAccount,
  removeAccountAvatar,
  setAccountName,
  uploadAccountAvatar,
} from "../apis/studio";
import type { Account } from "../types";

/** What the account is cached under. Every write here replaces it whole. */
export const ACCOUNT_KEY = ["account"] as const;

/** The answer before the request lands: nothing set, initials off the address. */
const EMPTY: Account = { name: null, avatar_url: null, updated_at: null };

/**
 * The signed-in person's name and picture, and the three writes that change them.
 *
 * **One read for the whole app.** The sidebar draws it in two shapes and the
 * dialog edits it, and React Query dedupes every asker onto one `GET`. Each
 * write answers with the whole record, which goes straight into the cache —
 * no invalidate-and-refetch, so the sidebar shows the new picture the moment
 * the upload answers rather than a round trip later.
 *
 * `account` is never undefined: before the request lands, and if it fails, it
 * is the empty record, and the sidebar draws the address. A person whose
 * picture cannot be fetched still has a name in the corner.
 *
 * The picture's URL is presigned and lasts the service's TTL, so the query is
 * refetched a little inside that — `staleTime` below — and the image beside
 * the name never goes 403 on a tab left open.
 */
export function useAccount() {
  const client = useQueryClient();
  const query = useQuery({
    queryKey: ACCOUNT_KEY,
    queryFn: getAccount,
    staleTime: 10 * 60 * 1000,
    refetchInterval: 10 * 60 * 1000,
  });

  const settle = (account: Account) => client.setQueryData(ACCOUNT_KEY, account);
  const rename = useMutation({ mutationFn: setAccountName, onSuccess: settle });
  const upload = useMutation({ mutationFn: uploadAccountAvatar, onSuccess: settle });
  const remove = useMutation({ mutationFn: removeAccountAvatar, onSuccess: settle });

  return {
    account: query.data ?? EMPTY,
    loading: query.isPending,
    rename,
    upload,
    remove,
  };
}

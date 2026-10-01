import { useCallback, useEffect, useState } from 'react';
import { stylistService } from '../services/apiServices';
import { Outfit, ShareLink } from '../models';
import { useUndoableRemove } from '../hooks/useUndoableRemove';
import { useUIStore } from '../stores/uiStore';
import { msg, detail } from '../i18n/messages';

type LoadState = 'loading' | 'ready' | 'error';

/**
 * My Looks — the saved-outfit collection and its share-link management.
 *
 * Audit context (2026-09-21): the /my-looks route rendered the *wardrobe*, so
 * saved outfits had no home in the UI at all, and there was no way to see or
 * revoke a share link that had already been published. Everything below binds
 * to the real endpoints; no state is optimistic-faked. In particular a look is
 * only shown as "shared" when the server reports a live token — never because
 * the user once pressed Share.
 */
export function useMyLooksViewModel() {
  const [looks, setLooks] = useState<Outfit[]>([]);
  const [state, setState] = useState<LoadState>('loading');
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [shareLinks, setShareLinks] = useState<Record<number, ShareLink>>({});
  const { showToast } = useUIStore();
  const undoableRemove = useUndoableRemove();

  const load = useCallback(async () => {
    setState('loading');
    try {
      const data = await stylistService.getSavedOutfits();
      setLooks(data);
      // Seed the share panel from the authoritative per-look fields the list
      // endpoint already returns, so opening the page does not require N+1
      // requests and cannot show a stale "shared" badge.
      const seeded: Record<number, ShareLink> = {};
      for (const look of data) {
        if (look.is_shared && look.share_url) {
          seeded[look.id] = {
            outfit_id: look.id,
            share_token: look.share_url.split('/').pop() ?? null,
            share_url: look.share_url,
            expires_at: look.share_expires_at ?? null,
            is_active: true,
            view_count: look.share_view_count ?? 0,
          };
        }
      }
      setShareLinks(seeded);
      setState('ready');
    } catch (err: any) {
      setError(err?.message ?? 'Could not load your looks.');
      setState('error');
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const share = useCallback(
    async (id: number, opts?: { rotate?: boolean }) => {
      setBusyId(id);
      try {
        const link = await stylistService.shareOutfit(id, opts);
        setShareLinks((prev) => ({ ...prev, [id]: link }));
        setLooks((prev) =>
          prev.map((l) =>
            l.id === id
              ? {
                  ...l,
                  is_shared: link.is_active,
                  share_url: link.share_url,
                  share_expires_at: link.expires_at,
                }
              : l,
          ),
        );
        showToast(
          msg(opts?.rotate ? 'toast.share_link_rotated' : 'toast.share_link_ready'),
          'success',
        );
        return link;
      } catch (err: any) {
        showToast(msg('toast.share_create_failed', { reason: detail(err) }), 'error');
        return null;
      } finally {
        setBusyId(null);
      }
    },
    [showToast],
  );

  const revoke = useCallback(
    async (id: number) => {
      setBusyId(id);
      try {
        await stylistService.revokeShare(id);
        setShareLinks((prev) => {
          const next = { ...prev };
          delete next[id];
          return next;
        });
        setLooks((prev) =>
          prev.map((l) =>
            l.id === id
              ? { ...l, is_shared: false, share_url: null, share_expires_at: null }
              : l,
          ),
        );
        showToast(msg('toast.look_revoked'), 'success');
      } catch (err: any) {
        showToast(msg('toast.share_revoke_failed', { reason: detail(err) }), 'error');
      } finally {
        setBusyId(null);
      }
    },
    [showToast],
  );

  const refreshShareState = useCallback(async (id: number) => {
    try {
      const link = await stylistService.getShareState(id);
      setShareLinks((prev) => ({ ...prev, [id]: link }));
      return link;
    } catch {
      return null;
    }
  }, []);

  /**
   * Remove a look WITH a real Undo.
   *
   * Delegates to the shared useUndoableRemove hook rather than repeating the
   * optimistic-remove / toast / restore / rollback dance that /wardrobe and
   * WardrobeView also need — three copies drift, and the user sees one
   * product. Reversible because the backend soft-deletes (migration 0031)
   * and exposes a real restore route; binning also revokes the look's public
   * share link immediately.
   */
  const remove = useCallback(
    async (id: number) => {
      const snapshot = looks;
      setBusyId(id);
      try {
        await undoableRemove({
          remove: () => stylistService.deleteOutfit(id),
          restore: () => stylistService.restoreOutfit(id),
          optimisticRemove: () => setLooks((prev) => prev.filter((l) => l.id !== id)),
          rollback: () => setLooks(snapshot),
          refetch: () => load(),
          messages: {
            removed: msg('toast.look_deleted'),
            removeFailed: (reason) => msg('toast.look_delete_failed', { reason }),
            restored: msg('toast.look_restored'),
            restoreFailed: (reason) => msg('toast.look_restore_failed', { reason }),
            removedPermanently: msg('toast.look_deleted_permanently'),
          },
        });
      } finally {
        setBusyId(null);
      }
    },
    [looks, load, undoableRemove],
  );

  const rename = useCallback(
    async (id: number, title: string) => {
      const clean = title.trim();
      if (!clean) return;
      try {
        const updated = await stylistService.updateOutfit(id, { title: clean });
        setLooks((prev) => prev.map((l) => (l.id === id ? { ...l, ...updated } : l)));
      } catch (err: any) {
        showToast(msg('toast.look_rename_failed', { reason: detail(err) }), 'error');
      }
    },
    [showToast],
  );

  return {
    looks,
    state,
    error,
    busyId,
    shareLinks,
    reload: load,
    share,
    revoke,
    refreshShareState,
    remove,
    rename,
  };
}

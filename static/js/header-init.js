import { refreshLedger } from './header.js';

// The ledger is shared chrome, so initialize it on every page that includes
// the topbar. Page modules may also request a refresh after mutations; the
// helper deduplicates concurrent initial requests.
refreshLedger().catch(() => {});

# Freeze vs tip timeline (truthful; immutable pins not rewritten)

## Prior (PID ownership V1 — superseded for Stop/Update safety)

- packaging_freeze=`59148ebd1d545aa887c4cb4a6288d9c8c394ba1b`
- feature_pid_ownership=`3c989facccc9443c351e0526dc76db7ee2f742a0`
- baseline_pre_fix=`2fcb5bf05cd61d47be93cbfbbbbb62ec4e16bddc`
- complete_sha256=`ddb9e7cd1afbe2661ba9bab1cc7de99fb419a695e43787c5f325c0846fc64e5e`
- complete_bytes=3835525
- full_sha256=`4a847207a6076efe62921198ae6bee317443da12ff099ef4b602f08366f7bbd4`

## Prior VT_BSTR packaging freeze (historical)

- baseline_vtbstr_freeze=`e18e3e234084bbc752366bbc22b011b416914115`

## This corrective (PID safety V2)

- baseline_pre_fix=`f441da40ade699021980ee636388be9eef42b68c` (independent RED 5/5)
- feature_pid_safety=`ae003b8f703e62144feb1eed77e0462b536d74dd`
- packaging_freeze=`0ea4264440bf330f005af7447bbd6bdb6cfabb46` (ZIP commit)
- note: PACKAGE_META inside COMPLETE records packaging_freeze_commit at build-time HEAD=`ae003b8…` (feature); the Git commit that stores the ZIPs is `0ea4264…`
- tip_url_pin=this tip commit after freeze
- complete_sha256=`58017ee3f09b5e6f21dd6097c390058ff48616cf83cc8b1932e93a32627a0e6a`
- complete_bytes=3873439
- full_sha256=`7bd8b000b43cbd832094582816f3c04a05af7585c934ed940c97623e85a10148`
- changed_sha256=`0c0a95f9ecfd1a6694db81b13ecae00a9969c3b6e88b4c3f51828aa4ae1ec37d`
- evidence_sha256=`ca57c50e6fedf9202a9c352aea6ea25c826804f85668f91a8bb8f9cd0a64c97f`
- baseline_pr26=`146d04cb930a446f891f48178a33672f0537b95e`
- GitHub Actions: report separately after push
- owner_windows_physical=`BLOCKED`
- do_not_start_until_independent_audit=`true`
- healthy_start_not_frame_pass=`true`

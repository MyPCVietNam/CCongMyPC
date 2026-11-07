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

- baseline_pre_fix=`f441da40ade699021980ee636388be9eef42b68c` (PR #27 tip at task start; independent RED 5/5)
- feature_pid_safety=`PENDING_FEATURE` (code+docs commit)
- packaging_freeze=`PENDING_FREEZE` (ZIP commit)
- tip_url_pin=`PENDING_TIP` (README raw URL + hashes after push verify)
- baseline_pr26=`146d04cb930a446f891f48178a33672f0537b95e`
- GitHub Actions: report separately after push
- owner_windows_physical=`BLOCKED`
- do_not_start_until_independent_audit=`true`
- healthy_start_not_frame_pass=`true`

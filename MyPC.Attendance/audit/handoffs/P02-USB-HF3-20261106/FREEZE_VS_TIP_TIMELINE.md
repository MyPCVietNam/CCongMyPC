# Freeze vs tip timeline (truthful naming)

Naming:
- **feature_commit** = last code/docs fix commit for this corrective (not a self-hash of the ZIP).
- **packaging_freeze_commit** = `HEAD` when the four delivery ZIPs were built (may equal feature if packaging docs ride along).
- **tip_after_push** = remote PR tip after freeze push (may advance if evidence-only follow-ups land).
- External pins below are prior immutable COMPLETE deliveries; they are not rewritten.

## V3 additional corrective (this release — independent 6 RED → GREEN)

- audited_v3_feature=`97c1e9df2d54314098066eca7c88c7e82edc4c79`
- audited_v3_packaging_freeze=`00858e3f78325517c43c4d688e5547748928b3a0`
- audited_v3_complete_sha256=`508f4fbc444f1ebb5fa7782a52ba8bb236448822e679718de344aeab10fce80f`
- audited_pr_tip_at_handoff=`ab1161dd87f0f363ea3974cf68c79b095ec11f03`
- baseline_pre_v3_additional=`e04a34121f3bf00253685a8512e2b835aa86b7ab` (Quality Guard tip before this fix)
- feature_commit / packaging_freeze / tip_after_push: filled at package time in `FEATURE_COMMIT.txt`, `PACKAGING_FREEZE_COMMIT.txt`, `REMOTE_PR_TIP.txt`, `PACKAGE_META.json`
- github_actions: record actual check-run URLs after Actions complete; else `UNRUN`/`BLOCKED`
- owner_windows_physical=`BLOCKED`

## Quality Guard v1.0 (prior on same PR)

- packaging_freeze=`66de411f35bcb2f4c011568524d7b0ce7fea9684`
- complete_sha256=`63dd0a57c1c3247b841e16e5e7e8aef93c3b521b55442be369ef2d2b849b03e0`

## Prior V3 / V2 / VT_BSTR

- v3_freeze=`00858e3f78325517c43c4d688e5547748928b3a0` complete=`508f4fbc…` (independent 6 RED on these pins)
- v3_feature=`97c1e9df2d54314098066eca7c88c7e82edc4c79`
- v2_freeze=`0ea4264440bf330f005af7447bbd6bdb6cfabb46` complete=`58017ee3…` (RED harness)
- vtbstr_freeze=`e18e3e234084bbc752366bbc22b011b416914115`

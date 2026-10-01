# Independent review: accepted cutover comment and checklist correction

Date: 2026-10-01. Initial correction: `0fc1e6c1affa41e078d9d70cd92a66907e36eb55`.
Sequencing correction: `c08ccaf6ffc8f311272babc1aca72ca419100891`.
Final reviewed correction: `00a129759ec49d2dff567f5f64e8b074fe98ef96`, relative to
hosted-tested source `e75207531664d94adadb02d34ad7144d052d3992`.
Reference contract: `43eee0da33dc6cfdd69d42ef84c3369dc49aabaf`.

## Verdict

**GO for focused source push and normal nondeploying hosted source checks.**
No unresolved substantive issue found in the requested documentation/comment
scope. This is not merge authority or permission to deploy, change triggers,
issue a canary grant, open sending or publish a release.

## Findings and closure

Initial `0fc1e6c` accurately corrected the HTTP lifetime and lease comments but
retained a checklist ordering inconsistency: migration preceded old-writer drain,
and another row required fenced traffic serving before the new runtime's intended
admission. Its Cron/Queue drain row also unnecessarily implied stopping unrelated
Queue consumers. These were reported directly to the implementation owner/root,
not silently edited in the owner's worktree.

`c08ccaf` closes those findings:

1. Held policy and writer/canary/grant freeze precede the baseline. The text does
   not mistake `check_send_hold.py` for proof of no outstanding one-use grant.
2. Old HTTP/service admission stops without prematurely serving the fenced runtime.
   Every relevant old invocation needs independently verified completion or
   provider-confirmed termination. Neither a generic wait nor a single-100 pin
   proves this termination.
3. Cron stop accounts for up-to-15-minute propagation, establishes the latest
   possible old start, then separately observes termination or waits the full
   documented Cron invocation window after that start. It does not start both
   windows at the source/config edit.
4. Quiescence and journal recheck precede migration; migration/schema verification
   precedes fenced single-100 runtime/config deployment. Cron remains paused,
   writer admission remains closed, and serving/binding/hold/schema readbacks
   precede bounded acceptance.
5. Required drain is Cron-only, not unrelated lifecycle/trace Queue shutdown.
   The explanatory statement that Queue invocations also have a 15-minute bound
   remains a factual platform comparison, not a new operational requirement.
6. Root identified a remaining `c08ccaf` final-row ambiguity: integrity acceptance
   appeared to permit existing Cron resume. `00a1297` explicitly keeps Cron paused
   until a separately reviewed resource-safe revision passes actual Paid/D1/CPU
   admission. Only separately resource-approved bounded acceptance is admitted;
   this PR's known LIMIT 20 handler is not authorized to resume by integrity success.

## Evidence and remaining boundaries

[Cloudflare Workers limits](https://developers.cloudflare.com/workers/platform/limits/)
explicitly give connected HTTP invocations no hard wall-time bound and distinguish
Cron/Queue wall time. [Cron configuration](https://developers.cloudflare.com/workers/configuration/cron-triggers/)
documents trigger-change propagation taking up to 15 minutes. The original
20-minute-lease assertion was therefore wrong for HTTP; corrected source and
migration comments now call it a finite retry window and rely on token checks
rather than assumed old-holder termination. No lease value, source predicate,
migration operation or test semantics changed in these correction commits.

The integrated cutover contract matches `43eee0d` byte-for-byte (Git blob
`3d0da9ba664e49d6953c459ad37b04686eaa7528`). Its Queue scope matches the inspected
`workers/mail-events` responsibility: attribute accepted/sent journals and persist
provider events/outcomes, not publish body/chunks or terminalize projection.

The hosted-result narrative explicitly attributes 89/89 workerd tests and six
source jobs to immutable `e752075`, not to an unexecuted final correction. This
review did not independently fetch Actions evidence; that source-run evidence
was supplied by root/implementation owner. The narrative requires normal checks
on the new final commit and explicitly denies deployed-provider, privacy, drain,
CPU/RSS, public-send and release acceptance. No false deployment claim was found.

Current CI still does not implement the full drain/schema/grant admission contract.
The known LIMIT 20 full-Cron budget counterexample remains outside the default
integrity suite and unresolved. The detailed linked contract and corrected final checklist row make resource and
privacy admission prerequisites explicit; synthetic hosted integrity success is
not a reason to bypass them or to resume unadmitted workload. GO depends on
retaining this explicit paused-Cron condition, not merely a fenced-runtime pin.

Validation performed here: targeted Git diffs, checklist/source inspection,
contract blob identity comparison, and `git diff e752075..00a1297 --check`.
No local project test/build, provider request or mutation, deploy, send, Queue
body read, workflow dispatch or push was performed. No production source edited.

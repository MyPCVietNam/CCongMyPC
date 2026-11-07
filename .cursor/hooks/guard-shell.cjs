'use strict';
/* Cursor beforeShellExecution hook; safe on Windows/Linux; Node 20+; no packages.
 * IMPORTANT: A command classifier cannot be a comprehensive sandbox. CI and OS
 * privileges, not hooks, are the final enforcement layers.
 */
const SAFE_READ_CMD = /^(?:rg|grep|git\s+(?:status|show|diff|log)|sed|cat|head|tail|Get-Content|Select-String)\b/i;
const SHELL_OPERATORS = /[;|&`><\n]|\$\(|\$\{/;

function classify(command) {
  if (typeof command !== 'string' || command.trim().length === 0 || command.length > 200000) {
    return { permission: 'deny', reason: 'Empty, missing or oversized shell command' };
  }
  const cmd = command.trim();
  // Allow ordinary reading of dangerous tokens in code, but only for a single
  // simple read-only command with no shell redirection or chaining.
  if (SAFE_READ_CMD.test(cmd) && !SHELL_OPERATORS.test(cmd)) {
    return { permission: 'allow', reason: 'Simple read-only inspection' };
  }
  const risks = [
    [/\b(?:Stop-Process|taskkill(?:\.exe)?|tskill(?:\.exe)?|killall|pkill)\b/i,
      'Live process termination requires owner operation, never agent/synthetic test'],
    [/(?:^|[;&|\n])\s*(?:sudo\s+)?kill\s+(?:-|\d)/i,
      'Direct OS process termination blocked'],
    [/\b(?:Remove-Item|rm|rmdir|del|erase)\b[^\r\n]*(?:-Recurse\b|-r[fi]+\b|-f?r\b|--recursive\b|\/s\b)/i,
      'Recursive or forced filesystem deletion blocked'],
    [/\bgit\s+(?:reset\s+--hard\b|clean\s+-[a-z]*f[a-z]*\b|push\b[^\r\n]*--force(?:-with-lease)?\b)/i,
      'Destructive Git operation blocked'],
    [/\b(?:diskpart(?:\.exe)?|format(?:\.com)?|Format-Volume|Clear-Disk|Initialize-Disk|bcdedit(?:\.exe)?)\b/i,
      'Boot/disk change blocked'],
    [/\b(?:Restart-Computer|Stop-Service|Remove-Service|shutdown(?:\.exe)?|sc(?:\.exe)?\s+(?:stop|delete)|net\s+stop)\b/i,
      'Service/power change blocked'],
    [/\b(?:p02_usb_hf[123]_candidate_18878\.ps1|p02_usb_hf3_pid_safety_runtime_tests\.ps1|Start-MyPCAttendance\.ps1|Stop-MyPCAttendance\.ps1)\b/i,
      'Owner Windows candidate/runtime script cannot be invoked by agent'],
    [/(?:curl|wget|Invoke-WebRequest|iwr)\b[^\r\n]*\|\s*(?:sh|bash|powershell|pwsh)\b/i,
      'Pipe-download-to-shell blocked'],
    [/\b(?:Set-ExecutionPolicy\s+Unrestricted|Set-MpPreference\s+-DisableRealtimeMonitoring)\b/i,
      'Weakening host security settings blocked'],
    [/\b(?:DataDir|FaceKey|CAMERA_LAB|secrets\.db|\.sqlite3?|\.onnx)\b[^\r\n]*\b(?:Remove-Item|rm|del|erase|Set-Content|Clear-Content)\b/i,
      'Owner-sensitive file mutation blocked'],
  ];
  for (const [pattern, reason] of risks) {
    if (pattern.test(cmd)) return { permission: 'deny', reason };
  }
  return { permission: 'allow', reason: 'No guarded side-effect pattern' };
}

function decide(payload) {
  if (!payload || typeof payload !== 'object') {
    return { permission: 'deny', user_message: 'MyPC guard: invalid hook payload' };
  }
  const command = payload.command;
  const result = classify(command);
  if (result.permission === 'deny') {
    return {
      permission: 'deny',
      user_message: `MyPC Quality Guard blocked command: ${result.reason}. Use an owner-approved runbook for host operations.`,
      agent_message: `Do not bypass guard. Replace OS side effects with mocks and CI/owner-lab separation. Reason: ${result.reason}.`,
    };
  }
  return { permission: 'allow' };
}

if (require.main === module) {
  let raw = '';
  process.stdin.setEncoding('utf8');
  process.stdin.on('data', chunk => { raw += chunk; if (raw.length > 250000) { raw = ''; process.stdout.write(JSON.stringify(decide(null))); process.exit(0); } });
  process.stdin.on('end', () => {
    let payload = null;
    try { payload = JSON.parse(raw); } catch (_) { /* deny */ }
    process.stdout.write(JSON.stringify(decide(payload)) + '\n');
  });
}
module.exports = { classify, decide };

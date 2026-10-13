using System;
using System.Diagnostics;
using System.IO;

// HookProbe - a git hook that git for Windows can actually execute.
//
// WHY THIS FILE IS PART OF THE LAB
// ================================
// The interesting question about git hooks is not "what does my hook script
// say" but "does git run it, in what order, with what arguments, and what does
// a failure do to the commit". Those questions are about git's dispatch, not
// about the hook's logic, so they need a hook that is nothing but dispatch.
//
// On Windows the dispatch rules are narrower than people assume:
//
//   * the program must be installed at `<hooks-dir>/<name>.exe`. git resolves
//     the hook name with `.exe`, so that one file is enough. (Measured.)
//   * an extensionless file is *found* as a hook but cannot be spawned:
//     CreateProcess only ever runs `.exe`, so the commit aborts with
//     `error: cannot spawn .git/hooks/pre-commit: No such file or directory`.
//   * a `pre-commit.bat` or `pre-commit.ps1` is IGNORED - not an error, just
//     ignored. Measured: commits succeed and the file never runs.
//   * a hook file whose first line is a shebang is handed to `sh`. On the
//     machine this lab was written on, MSYS `sh.exe` cannot start at all
//     (`fatal error - couldn't create signal pipe, Win32 error 5`), so every
//     sh-based hook is unusable there.
//   * a real PE executable installed as described above runs natively. That
//     makes this probe the only way to observe hook dispatch end to end here.
//
// One binary serves every hook: it identifies itself from its own filename, so
// the same .exe can be copied to pre-commit.exe, prepare-commit-msg.exe,
// commit-msg.exe and post-commit.exe and still report which one git called.
//
// ENVIRONMENT
//   PROBE_LOG                append one line per run to this file
//   PROBE_EXIT_<HOOK_NAME>   exit code for this hook (default 0).
//                            e.g. PROBE_EXIT_PRE_COMMIT=7
//
// OUTPUT
//   One appended log line:  <hook>|args=<n>|<file|nofile|->|exit=<n>|<time>
//   plus a line on stderr, so the transcript shows git's own hook output too.
public class HookProbe
{
    public static int Main(string[] args)
    {
        string self = Process.GetCurrentProcess().MainModule.FileName;
        string name = Path.GetFileNameWithoutExtension(self);
        string key = "PROBE_EXIT_" + name.Replace("-", "_").ToUpperInvariant();
        string raw = Environment.GetEnvironmentVariable(key);

        int code = 0;
        if (!string.IsNullOrEmpty(raw))
        {
            int.TryParse(raw, out code);
        }

        string log = Environment.GetEnvironmentVariable("PROBE_LOG");
        if (!string.IsNullOrEmpty(log))
        {
            // The first argument of prepare-commit-msg and commit-msg is a real
            // file git has just written. Recording whether it exists proves the
            // argument is actually delivered, not merely documented.
            string argInfo = "-";
            if (args.Length > 0 && args[0].Length > 0)
            {
                argInfo = File.Exists(args[0]) ? "file" : "nofile";
            }

            string line = name
                + "|args=" + args.Length
                + "|" + argInfo
                + "|exit=" + code
                + "|" + DateTime.UtcNow.ToString("HH:mm:ss.fff")
                + Environment.NewLine;

            // A `post-commit` hook that throws would be a confusing failure, so
            // logging failures are reported on stderr instead of crashing.
            try
            {
                File.AppendAllText(log, line);
            }
            catch (Exception exc)
            {
                Console.Error.WriteLine("[probe] could not write log: " + exc.Message);
            }
        }

        Console.Error.WriteLine("[probe] " + name + " ran, exiting " + code);
        return code;
    }
}

using System;
using System.Diagnostics;

namespace Demo
{
    public class Handler
    {
        private const string ApiKey = "AKIAIOSFODNN7REALKEYS";

        public void Run(string user)
        {
            // TODO: rotate the leaked key
            System.Diagnostics.Process.Start("cmd.exe", "/c " + user);
            var rows = $"SELECT * FROM users WHERE name={user}";
            var lookup = string.Format("SELECT * FROM logs WHERE ip = '{0}'", user);
            var names = "SELECT id FROM accounts WHERE owner = " + user;
            var total = CSharpScript.EvaluateAsync("1 + 1");
            var psi = new ProcessStartInfo { UseShellExecute = true };
        }
    }
}

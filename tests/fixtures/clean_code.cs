using System;
using System.Data;

namespace Demo
{
    public class UserRepository
    {
        public int CountUsers(IDbConnection db, string name)
        {
            using var cmd = db.CreateCommand();
            cmd.CommandText = "SELECT COUNT(*) FROM users WHERE name = @name";
            return 0;
        }
    }
}

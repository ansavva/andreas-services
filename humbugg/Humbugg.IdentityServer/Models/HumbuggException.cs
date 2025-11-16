using System;

namespace Humbugg.IdentityServer.Models
{
    public class HumbuggException : Exception
    {
        public HumbuggException() : base() {}
        public HumbuggException(string message) : base(message) {}
    }
}
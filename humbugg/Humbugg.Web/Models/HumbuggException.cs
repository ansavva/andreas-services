using System;

namespace Humbugg.Web.Models
{
    public class HumbuggException : Exception
    {
        public HumbuggException() : base() {}
        public HumbuggException(string message) : base(message) {}
    }
}
using System;

namespace Humbugg.Api.Models
{
    public class HumbuggException : Exception
    {
        public HumbuggException() : base() {}
        public HumbuggException(string message) : base(message) {}
    }
}
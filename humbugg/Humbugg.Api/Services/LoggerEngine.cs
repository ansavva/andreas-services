using Serilog;
using System;

namespace Humbugg.Api.Services
{
    public interface ILoggerEnigne
    {
        void Info(string messageTemplate, params object[] propertyValues);
        void Error(Exception exception, string messageTemplate, params object[] propertyValues);
        void Error(string messageTemplate, params object[] propertyValues);
        void Warn(string messageTemplate, params object[] propertyValues);
        void Debug(string messageTemplate, params object[] propertyValues);
        void Fatal(Exception exception, string messageTemplate, params object[] propertyValues);
        void Fatal(string messageTemplate, params object[] propertyValues);
    }

    public class LoggerEngine : ILoggerEnigne
    {
        private readonly ILogger _logger;

        public LoggerEngine(ILogger logger)
        {
            _logger = logger;
        }

        public void Info(string messageTemplate, params object[] propertyValues) => _logger.Information(messageTemplate, propertyValues);
        public void Error(Exception exception, string messageTemplate, params object[] propertyValues) => _logger.Error(exception, messageTemplate, propertyValues);
        public void Error(string messageTemplate, params object[] propertyValues) => _logger.Error(messageTemplate, propertyValues);
        public void Warn(string messageTemplate, params object[] propertyValues) => _logger.Warning(messageTemplate, propertyValues);
        public void Debug(string messageTemplate, params object[] propertyValues) => _logger.Debug(messageTemplate, propertyValues);
        public void Fatal(Exception exception, string messageTemplate, params object[] propertyValues) => _logger.Fatal(exception, messageTemplate, propertyValues);
        public void Fatal(string messageTemplate, params object[] propertyValues) => _logger.Fatal(messageTemplate, propertyValues);
    }
}

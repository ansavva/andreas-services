
using System;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Text;
using System.Threading.Tasks;
using Newtonsoft.Json;

namespace Humbugg.Web.Services
{
    public interface IHttpClientService
    {
        Task<TResponse> GetAsync<TResponse>(string accessToken, string requestUrl);
        Task<TResponse> PostAsync<TRequest, TResponse>(string accessToken, string requestUrl, TRequest data);
        Task<TResponse> PutAsync<TRequest, TResponse>(string accessToken, string requestUrl, TRequest data);
        Task<TResponse> DeleteAsync<TResponse>(string accessToken, string requestUrl);
    }

    public class HttpClientService : IHttpClientService
    {
        private readonly HttpClient _client;

        public HttpClientService(string apiUrl)
        {
            _client = new HttpClient();
            _client.BaseAddress = new Uri(apiUrl);
        }

        public async Task<TResponse> GetAsync<TResponse>(string accessToken, string requestUrl)
        {
            _client.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", accessToken);
            var response = await _client.GetAsync(requestUrl);
            return await ConvertResponse<TResponse>(response);
        }

        public async Task<TResponse> PostAsync<TRequest, TResponse>(string accessToken, string requestUrl, TRequest data)
        {
            _client.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", accessToken);
            var response = await _client.PostAsync(requestUrl, ConvertRequest(data));
            return await ConvertResponse<TResponse>(response);
        }

        public async Task<TResponse> PutAsync<TRequest, TResponse>(string accessToken, string requestUrl, TRequest data)
        {
            _client.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", accessToken);
            var response = await _client.PutAsync(requestUrl, ConvertRequest(data));
            return await ConvertResponse<TResponse>(response);
        }

        public async Task<TResponse> DeleteAsync<TResponse>(string accessToken, string requestUrl)
        {
            _client.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", accessToken);
            var response = await _client.DeleteAsync(requestUrl);
            return await ConvertResponse<TResponse>(response);
        }

        private StringContent ConvertRequest<TRequest>(TRequest data)
        {
            var requestData = JsonConvert.SerializeObject(data);
            var content = new StringContent(requestData, Encoding.UTF8, "application/json");
            return content;
        }

        private async Task<TResponse> ConvertResponse<TResponse>(HttpResponseMessage response)
        {
            response.EnsureSuccessStatusCode();
            string responseBody = await response.Content.ReadAsStringAsync();
            if (responseBody != null && responseBody != "")
            {
                return JsonConvert.DeserializeObject<TResponse>(responseBody);
            }
            return default(TResponse);
        }
    }
}
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Humbugg.Web.Models;
using Humbugg.Web.Services;
using System.Threading.Tasks;
using Microsoft.AspNetCore.Authentication;

namespace Humbugg.Web.Controllers
{
    [Route("/api/[controller]")]
    [Authorize]
    public class ProfileController : Controller
    {
        private readonly IHttpClientService _httpClientService;

        public ProfileController(IHttpClientService httpClientService)
        {
            _httpClientService = httpClientService;
        }
        
        [HttpGet("")]
        public async Task<ActionResult<Profile>> Get()
        {
            var accessToken = await HttpContext.GetTokenAsync("access_token");
            var profile = await _httpClientService.GetAsync<Profile>(accessToken, "/api/profile");
            if (profile == null) return NotFound();
            return profile;
        }

        [HttpGet("{id}")]
        public async Task<ActionResult<Profile>> Get(string id)
        {
            var accessToken = await HttpContext.GetTokenAsync("access_token");
            var profile = await _httpClientService.GetAsync<Profile>(accessToken, $"/api/profile/{id}");
            if (profile == null) return NotFound();
            return profile;
        }

        [HttpPost]
        public async Task<ActionResult<Profile>> Create([FromBody]Profile profile)
        {
            var accessToken = await HttpContext.GetTokenAsync("access_token");
            var profileData = await _httpClientService.PostAsync<Profile, Profile>(accessToken, "/api/profile", profile);
            return await Get(profileData.Id);
        }

        [HttpPut("{id}")]
        public async Task<IActionResult> Update(string id, [FromBody]Profile  profile)
        {
            var accessToken = await HttpContext.GetTokenAsync("access_token");
            await _httpClientService.PutAsync<Profile, string>(accessToken, $"/api/profile/{id}", profile);
            return NoContent();
        }

        [HttpDelete("{id}")]
        public async Task<IActionResult> Delete(string id)
        {
            var accessToken = await HttpContext.GetTokenAsync("access_token");
            await _httpClientService.DeleteAsync<string>(accessToken, $"/api/profile/{id}");
            return NoContent();
        }
    }
}
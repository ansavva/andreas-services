using System.Collections.Generic;
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
    public class GroupController : Controller
    {
        private readonly IHttpClientService _httpClientService;

        public GroupController(IHttpClientService httpClientService)
        {
            _httpClientService = httpClientService;
        }

        [HttpGet("")]
        public async Task<ActionResult<List<Group>>> Get()
        {            
            var accessToken = await HttpContext.GetTokenAsync("access_token");
            var groups = await _httpClientService.GetAsync<List<Group>>(accessToken, "/api/group");
            if (groups == null) return NotFound();
            return groups;
        }

        [HttpGet("{id}")]
        public async Task<ActionResult<Group>> Get(string id)
        {
            var accessToken = await HttpContext.GetTokenAsync("access_token");
            var group = await _httpClientService.GetAsync<Group>(accessToken, $"/api/group/{id}");
            if (group == null) return NotFound();
            return group;
        }
 
        [HttpGet("createMatches/{id}")]
        public async Task<ActionResult<Group>> CreateMatches(string id)
        {
            var accessToken = await HttpContext.GetTokenAsync("access_token");
            var newGroup = await _httpClientService.GetAsync<Group>(accessToken, $"/api/group/createMatches/{id}");
            if (newGroup == null) return NotFound();
            return newGroup;
        }

        [HttpPost]
        public async Task<ActionResult<Group>> Create([FromBody]Group group)
        {
            var accessToken = await HttpContext.GetTokenAsync("access_token");
            var groupData = await _httpClientService.PostAsync<Group, Group>(accessToken, "/api/group", group);
            return await Get(groupData.Id);
        }

        [HttpPut("{id}")]
        public async Task<IActionResult> Update(string id, [FromBody]Group group)
        {
            var accessToken = await HttpContext.GetTokenAsync("access_token");
            await _httpClientService.PutAsync<Group, string>(accessToken, $"/api/group/{id}", group);
            return NoContent();
        }

        [HttpDelete("{id}")]
        public async Task<IActionResult> Delete(string id)
        {
            var accessToken = await HttpContext.GetTokenAsync("access_token");
            await _httpClientService.DeleteAsync<string>(accessToken, $"/api/group/{id}");
            return NoContent();
        }
    }
}
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
    public class GroupMemberController : Controller
    {
        private readonly IHttpClientService _httpClientService;

        public GroupMemberController(IHttpClientService httpClientService)
        {
            _httpClientService = httpClientService;
        }

        [HttpGet("")]
        public async Task<ActionResult<List<GroupMember>>> Get()
        {
            var accessToken = await HttpContext.GetTokenAsync("access_token");
            var groupMembers = await _httpClientService.GetAsync<List<GroupMember>>(accessToken, "/api/groupMember");
            if (groupMembers == null) return NotFound();
            return groupMembers;
        }

        [HttpGet("{id}")]
        public async Task<ActionResult<GroupMember>> Get(string id)
        {
            var accessToken = await HttpContext.GetTokenAsync("access_token");
            var groupMember =  await _httpClientService.GetAsync<GroupMember>(accessToken, $"/api/groupMember/{id}");
            if (groupMember == null) return NotFound();
            return groupMember;
        }

        [HttpPost]
        public async Task<ActionResult<GroupMember>> Create([FromBody]GroupMember groupMember)
        {
            var accessToken = await HttpContext.GetTokenAsync("access_token");
            var groupMemberData = await _httpClientService.PostAsync<GroupMember, GroupMember>(accessToken, "/api/groupMember", groupMember);
            return await Get(groupMemberData.Id);
        }

        [HttpPut("{id}")]
        public async Task<IActionResult> Update(string id, [FromBody]GroupMember groupMember)
        {
            var accessToken = await HttpContext.GetTokenAsync("access_token");
            await _httpClientService.PutAsync<GroupMember, string>(accessToken, $"/api/groupMember/{id}", groupMember);
            return NoContent();
        }

        [HttpDelete("{id}")]
        public async Task<IActionResult> Delete(string id)
        {
            var accessToken = await HttpContext.GetTokenAsync("access_token");
            await _httpClientService.DeleteAsync<string>(accessToken, $"/api/groupMember/{id}");
            return NoContent();
        }
    }
}
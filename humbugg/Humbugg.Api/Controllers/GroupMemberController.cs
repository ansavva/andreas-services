using System.Collections.Generic;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Humbugg.Api.Services;
using Humbugg.Api.Models;

namespace Humbugg.Api.Controllers
{
    [ApiController]
    [Route("/api/[controller]")]
    [Authorize]
    public class GroupMemberController : ControllerBase
    {
        private readonly IGroupMemberEngine _groupMemberEngine;

        public GroupMemberController(IGroupMemberEngine groupMemberEngine)
        {
            _groupMemberEngine = groupMemberEngine;
        }

        [HttpGet("")]
        public ActionResult<List<GroupMember>> Get()
        {
            var groupMembers = _groupMemberEngine.GetByUserId();
            if (groupMembers == null)
            {
                return NotFound();
            }
            return groupMembers;
        }

        [HttpGet("{id}")]
        public ActionResult<GroupMember> Get(string id)
        {
            var groupMember = _groupMemberEngine.GetById(id);
            if (groupMember == null)
            {
                return NotFound();
            }
            return groupMember;
        }

        [HttpPost]
        public ActionResult<GroupMember> Create([FromBody]GroupMember groupMember)
        {
            _groupMemberEngine.Create(groupMember);
            return Get(groupMember.Id);
        }

        [HttpPut("{id}")]
        public IActionResult Update(string id, [FromBody]GroupMember groupMember)
        {
            var groupMemberFound = _groupMemberEngine.GetById(id);
            if (groupMemberFound == null)
            {
                return NotFound();
            }
            _groupMemberEngine.Update(id, groupMember);
            return NoContent();
        }

        [HttpDelete("{id}")]
        public IActionResult Delete(string id)
        {
            var groupMemberFound = _groupMemberEngine.GetById(id);
            if (groupMemberFound == null)
            {
                return NotFound();
            }
            _groupMemberEngine.Remove(id);
            return NoContent();
        }
    }
}
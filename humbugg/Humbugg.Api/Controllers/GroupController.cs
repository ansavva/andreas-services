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
    public class GroupController : ControllerBase
    {
        private readonly IGroupEngine _groupEngine;

        public GroupController(IGroupEngine groupEngine)
        {
            _groupEngine = groupEngine;
        }

        [HttpGet("")]
        public ActionResult<List<Group>> Get()
        {
            var groups = _groupEngine.Get();
            if (groups == null)
            {
                return NotFound();
            }
            return groups;
        }

        [HttpGet("{id}")]
        public ActionResult<Group> Get(string id)
        {
            var group = _groupEngine.Get(id);
            if (group == null)
            {
                return NotFound();
            }
            return group;
        }
 
        [HttpGet("createMatches/{id}")]
        public ActionResult<Group> CreateMatches(string id)
        {
            _groupEngine.CreateMatches(id);
            return Get(id);
        }

        [HttpPost]
        public ActionResult<Group> Create([FromBody]Group group)
        {
           _groupEngine.Create(group);
            return Get(group.Id);
        }

        [HttpPut("{id}")]
        public IActionResult Update(string id, [FromBody]Group group)
        {
            var groupMemberFound = _groupEngine.Get(id);
            if (groupMemberFound == null)
            {
                return NotFound();
            }
            _groupEngine.Update(id, group);
            return NoContent();
        }

        [HttpDelete("{id}")]
        public IActionResult Delete(string id)
        {
            var groupFound = _groupEngine.Get(id);
            if (groupFound == null)
            {
                return NotFound();
            }
            _groupEngine.Remove(id);
            return NoContent();
        }
    }
}
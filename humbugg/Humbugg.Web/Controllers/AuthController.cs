using Microsoft.AspNetCore.Authentication;
using Microsoft.AspNetCore.Authentication.Cookies;
using Microsoft.AspNetCore.Authentication.OpenIdConnect;
using Microsoft.AspNetCore.Mvc;

namespace Humbugg.Web.Controllers
{
    [Route("auth")]
    public class AuthController : Controller
    {
        [HttpGet("isAuthenticated")]
        public IActionResult IsAuthenticated()
        {
            return new ObjectResult(User.Identity.IsAuthenticated);
        }
        
        [Route("signin")]
        public IActionResult SignIn(string returnUrl = null)
        {
            if (returnUrl == null) returnUrl = "/";
            return Challenge(new AuthenticationProperties { RedirectUri = returnUrl });
        }
        
        [Route("signout")]
        public IActionResult Logout()
        {
            return SignOut(CookieAuthenticationDefaults.AuthenticationScheme, OpenIdConnectDefaults.AuthenticationScheme);
        }
    }
}
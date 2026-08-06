# DuckDuckGo search: tailscale Funnel limits vs Serve Windows support

## 1. Tailscale Funnel · Tailscale Docs
<https://tailscale.com/docs/features/tailscale-funnel>

Traffic sent over a Funnel is subject to non-configurable bandwidth limits. Funnel only works on platforms that can run the Tailscale CLI. To use Funnel on macOS, you must use one of the open source variants of the Tailscale application for macOS. The same port number cannot be used for Serve (available only within the tailnet) and Funnel (available within the tailnet and to the public) at the same time.

## 2. Tailscale Serve · Tailscale Docs
<https://tailscale.com/docs/features/tailscale-serve>

By listening only on localhost, this limits tampering to only other services running on the Serve device, and not anyone on your LAN or tailnet. Serve traffic can be configured to forward a header with selected app capabilities of the connected user or tagged device. Similar to identity headers, this isn't available for Funnel traffic, which is publicly available.

## 3. Reintroducing Serve and Funnel: even simpler sharing with your tailnet (or the world!)
<https://tailscale.com/blog/reintroducing-serve-funnel>

October 30, 2023 - Learn more about how Funnel works behind the scenes. Tailscale Serve is a lot like Funnel, but instead of serving content to the entire internet, it’s only accessible to other devices and people in your tailnet. If you want to share a service or a directory or a page with all of your machines and the members of your team, no matter where they are in the world, Serve can help you do so privately and securely.

## 4. Serve and Funnel | tailscale/tailscale | DeepWiki
<https://deepwiki.com/tailscale/tailscale/7.4-serve-and-funnel>

Jul 22, 2026 · The tailscale serve and tailscale funnel commands allow users to expose local services either within their tailnet or to the public internet. This functionality is implemented through a combination of configuration management in LocalBackend, TCP/HTTP request interception, and coordination with Tailscale's ingress infrastructure.

## 5. tailscale funnel command · Tailscale Docs
<https://tailscale.com/docs/reference/tailscale-cli/funnel>

tailscale funnel lets you share a local service over the internet. You can also choose to use Tailscale Serve using the tailscale serve command to limit sharing within your tailnet.

## 6. tailscale serve command · Tailscale Docs
<https://tailscale.com/docs/reference/tailscale-cli/serve>

tailscale serve lets you share a local service securely within your Tailscale network (known as a tailnet). ... You can also choose to use Tailscale Funnel with the tailscale funnel command to expose your service publicly, open to the entire internet.

## 7. Tailscale · OpenClaw
<https://docs.openclaw.ai/gateway/tailscale>

Serve injects Tailscale identity headers; Funnel does not. Funnel requires Tailscale v1.38.3+, MagicDNS, HTTPS enabled, and a funnel node attribute. Funnel only supports ports 443, 8443, and 10000 over TLS.

## 8. Tailscale Funnel | Foundry VTT Community Wiki
<https://foundryvtt.wiki/en/setup/hosting/tailscale>

While Tailscale don't have a history of removing beta features, they could in theory adjust access to the feature or remove it at any time, and will not guarantee any level of technical support. They may also make breaking changes to the feature, but will give some advance warning in these cases. I've been using Tailscale Funnel for other services for the last year without any issues, but your mileage may vary. There is also a bandwidth limit to Tailscale Funnel, which is undisclosed, but in my testing I have never hit this limit even with streaming 4k video.

## 9. Tailscale Port Forwarding: Serve, Funnel & Firewall Ports
<https://natchecker.com/blog/tailscale-port-forwarding>

Jul 29, 2026 · Learn whether Tailscale needs port forwarding, which firewall ports help direct connections, and when to use Serve, Funnel, or a VPN with port forwarding.

## 10. Tailscale Funnel vs Serve: when should services stay private?
<https://nhimg.org/community/cybersecurity-beyond-identity/tailscale-funnel-vs-serve-when-should-services-stay-private/>

5 days ago · TL;DR: Small, public-facing web apps are a fit for open exposure, but personal services, dashboards, and AI-like systems with sensitive data belong behind Serve instead, because public certificates, scanability, and password-only defence change the risk profile, according to Tailscale. The broader lesson is that convenience cannot be the governance model when access boundaries carry real ...

## 11. Expose local services to your Tailnet and beyond with Serve ...
<https://www.ryantiffany.com/expose-local-services-to-your-tailnet-and-beyond-with-serve-and-funnel/>

Dec 11, 2024 · Thanks Tailscale Magic DNS! Tailscale Funnel While Serve exposed our local service to devices on our Tailnet, the Funnel service allows us to route traffic from the wider internet to the local service running in the Tailnet. This means anyone with the URL can interact with the service.

## 12. Funnel serve multiple ports? : r/Tailscale - Reddit
<https://www.reddit.com/r/Tailscale/comments/14gccua/funnel_serve_multiple_ports/>

You can serve Funnel over ports 443, 8443, or 10000. This is currently listed as a limitation. Alternatively, you can serve multiple applications over different paths. For the following examples, let's assume you have applications running locally on port 3000 and port 8000.

## 13. Tailscale Funnel, Serve, and a tiny website for my fridge
<https://tailscale.com/blog/funnel-fridge>

June 2, 2026 - Our guide to setting up remote access to Home Assistant through Tailscale has you setting up Tailscale Serve, not Funnel. "I really wouldn't recommend exposing your Home Assistant instance to the wider internet," host Alex Kretzschmar says. "There's just no need with Tailscale." If someone getting past a password would be a disaster, use Serve instead. Set up Serve, then connect through devices running Tailscale. If Serve feels limiting because you want a few other people to access your site or service, consider adding them as a user on your tailnet, or sharing that device to their own Tailscale account.

## 14. Tailscale Concepts: Serve, Funnel, and MagicDNS | tailscale-dev/ScaleTail | DeepWiki
<https://deepwiki.com/tailscale-dev/ScaleTail/1.2-tailscale-concepts:-serve-funnel-and-magicdns>

April 25, 2026 - While Serve is restricted to your private Tailnet, Funnel routes traffic from the public internet through Tailscale-managed relay nodes to your local sidecar.

## 15. Tailscale Serve vs Funnel - ScaleTail
<https://mintlify.wiki/tailscale-dev/ScaleTail/configuration/serve-vs-funnel>

March 4, 2026 - For Funnel services, monitor access logs and set up alerts for suspicious activity. With Serve, use Tailscale ACLs to restrict which Tailnet members can access specific services.

## 16. I've used serve/funnel on the tailscale free tier... definitely agree that the t... | Hacker News
<https://news.ycombinator.com/item?id=47064330>

February 19, 2026 - Ok I checked the pricing page and funnel is available in the free tier (limited to 3 users) but not the $6/user/month tier - which you need for more than 6 users... strange pricing structure but I guess I see the logic · Any chance you were asked to upgrade from $6/user/month to $18/user/month ...

## 17. r/Tailscale on Reddit: Reintroducing Serve and Funnel: even simpler sharing with your tailnet (or the world!)
<https://www.reddit.com/r/Tailscale/comments/17k3teu/reintroducing_serve_and_funnel_even_simpler/>

October 30, 2023 - You mention that I can run funnel multiple times, but I get the following error wanting to expose >1 service that are running locally on different ports: ... $ tailscale funnel --set-path=/api 8001 background configuration already exists, use \`tailscale funnel --https=443 off\` to remove the existing configuration

## 18. tailscale-docs/features/tailscale-funnel/index.md at master · Chesszyh/tailscale-docs
<https://github.com/Chesszyh/tailscale-docs/blob/master/features/tailscale-funnel/index.md>

Traffic sent over a Funnel is subject to non-configurable bandwidth limits. Funnel only works on platforms that can run the Tailscale CLI. To use Funnel on macOS, you must use one of the open source variants of the Tailscale application for macOS. The same port number cannot be used for Serve (available only within the tailnet) and Funnel (available within the tailnet and to the public) at the same time.

## 19. Tailscale Feature Highlight: SSH, Serve, and Funnel – runtimeterror
<https://www.runtimeterror.dev/tailscale-ssh-serve-funnel/>

December 20, 2023 - If I want to make the netdata instance available publicly while keeping Cockpit internal-only, I'll need to serve netdata on a different port. Funnel only supports↗ ports 443, 8443, and 10000, so I'll use 8443:

## 20. r/Tailscale on Reddit: Use Tailscale Serve and Funnel to publish a Dockerised web application to your intranet (tailnet)…
<https://www.reddit.com/r/Tailscale/comments/1e23n65/use_tailscale_serve_and_funnel_to_publish_a/>

July 13, 2024 - I've set up serve (while disactivating funnel) last week so I could access a container through https and my *.ts.net address and... It just works. Tailscale style!

## 21. Funnel issues? : r/Tailscale - Reddit
<https://www.reddit.com/r/Tailscale/comments/1todp0w/funnel_issues/>

26 May 2026 ... Keep in mind that funnel exposes the service to the public Internet, losing the benefits of running it behind Tailscale. You can share out your ...

## 22. Tailscale Funnel now available in beta - Hacker News
<https://news.ycombinator.com/item?id=35374302>

30 Mar 2023 ... Tailscalar here: there is a bandwidth limit, it's a funnel, not a hose. We don't announce what the bandwidth limit is, but please keep in mind ...

## 23. Funnel through Custom DERP · Issue #15203 · tailscale ... - GitHub
<https://github.com/tailscale/tailscale/issues/15203>

4 Mar 2025 ... I'm exploring the possibility of using Tailscale Funnel in conjunction with a custom DERP server to potentially bypass bandwidth limitations ...

## 24. Tailscale pricing
<https://tailscale.com/pricing>

For individuals who want to securely connect devices, servers, or software. Access nearly all of Tailscale's offerings and products for free, indefinitely. $0 ...

## 25. Serve and Funnel | Tailscale Explained - YouTube
<https://www.youtube.com/watch?v=MpxmfpCl20c>

In our "Tailscale Explained" series we show you all you need to know to get started on a particular area or feature of Tailscale. In today's video we cover off Tailscale Serve and Tailscale Funnel.

## 26. Funnels vs Tunnels: Replacing ngrok with Tailscale... | InstaTunnel Blog
<https://instatunnel.my/blog/funnels-vs-tunnels-rethinking-ngrok-tailscale-and-cloudflare-for-zero-trust-infrastructure>

Funnels vs. Tunnels: Rethinking ngrok, Tailscale, and Cloudflare for Zero-Trust Infrastructure. IT. InstaTunnel Team.Tailscale describes Funnel traffic as subject to non-configurable bandwidth limits, without stating the number. The same port can’t run Serve and Funnel at once.

## 27. Tailscale Funnel vs Cloudflare Tunnel vs Nginx... - Onidel Cloud
<https://onidel.com/tailscale-cloudflare-nginx-vps-2025/>

Compare Tailscale Funnel, Cloudflare Tunnel, and Nginx on VPS for latency, security, and use cases in 2025. Optimize with Onidel.

## 28. Tailscale funnel is the most useful and underrated Tailscale feature
<https://www.xda-developers.com/tailscale-funnel-is-amazing/>

tailscale funnel [port]. The terminal window will show the new URL to connect to that service from, and any data transmitted between a browser using that URL and the service on your server is fully encrypted end-to-end, keeping you safe.

## 29. Access Local Web Apps Securely with Tailscale
<https://blog.openreplay.com/secure-local-web-apps-tailscale/>

Tailscale Serve exposes a local service — say, a dev server running on localhost:3000 — to other devices inside your tailnet. It’s the right tool when your audience is your team, not the public internet. To share a local web app with your teammates, run

## 30. Securely route internet traffic to local services using Tailscale Funnel.
<https://tailscale-com.nproxy.org/docs/features/tailscale-funnel>

Toggle. Tailscale Serve.Tailscale Funnel lets you route traffic from the broader internet to a local service running on a device in your Tailscale network (known as a tailnet). You can use it to share a local service, like a web app, for anyone to access—even if they don't use Tailscale.

## 31. Tailscale as an ngrok / local tunnel / Cloudflare... | Chris Shennan
<https://chrisshennan.com/blog/tailscale-as-an-ngrok-local-tunnel-cloudflare-tunnel-alternative>

Tailscale Serve vs Tailscale Funnel — know the difference. This is the bit that cost me the most time. Tailscale has two related but distinct commands: tailscale serve — exposes a local service to other devices on your own tailnet only.

## 32. Tailscale Funnel: Expose Homelab Services... — HomeLab Starter
<https://homelabstarter.com/homelab-tailscale-funnel/>

How to use Tailscale Funnel to share homelab services on the public internet — no port forwarding, no domain name, no exposed home IP. Covers setup, HTTPS handling, limitations, and comparison with Cloudflare Tunnels and ngrok.

## 33. Exposing LDE to the Internet using TailScale
<https://www.linkedin.com/pulse/exposing-lde-internet-using-tailscale-ajith-thampi-joseph-nombc>

Tailscale Serve vs. Funnel. Tailscale provides two features for sharing a webserver: Tailscale Serve and Tailscale Funnel. Sharing is also kind of an option, but It is more of a one-one than one-many.

## 34. tunnels.io vs Tailscale: public URL vs private mesh
<https://tunnels.io/compare/tailscale>

tunnels.io vs Tailscale. Tailscale connects your machines.Tailscale's own words: "Tailscale Funnel lets you route traffic from the broader internet to a local service running on a device in your Tailscale network (known as a tailnet).

## 35. GitHub - tailscale-dev/ScaleTail: Tailscale Sidecar Configurations for...
<https://github.com/tailscale-dev/ScaleTail>

Tailscale Funnel vs. Tailscale Serve. Tailscale Funnel securely exposes services to the public internet.Tailscale Serve is a feature that lets you route traffic from other devices on your Tailscale network (known as a Tailnet) to a local service running on your device.

## 36. OpenClaw + Tailscale: Secure Setup for Always-On AI... | All Claw
<https://allclaw.org/blog/openclaw-tailscale>

Official integration auto-configures Tailscale Serve (tailnet-only HTTPS) or Tailscale Funnel (public with password) while keeping the Gateway bound to loopback for maximum security.

## 37. r/Tailscale on Reddit: Can funnel be moved to services?
<https://www.reddit.com/r/Tailscale/comments/1p3xwge/can_funnel_be_moved_to_services/>

## 38. r/Tailscale on Reddit: Tailscale Funnel limitations
<https://www.reddit.com/r/Tailscale/comments/1g85shq/tailscale_funnel_limitations/>

## 39. r/Tailscale on Reddit: What are the advantages of using Tailscale funnel vs port forwarding?
<https://www.reddit.com/r/Tailscale/comments/1pchfhw/what_are_the_advantages_of_using_tailscale_funnel/>

## 40. r/Tailscale on Reddit: So... what exactly IS Tailscale serve?
<https://www.reddit.com/r/Tailscale/comments/1bbkvel/so_what_exactly_is_tailscale_serve/>

## 41. 5 reasons I love Tailscale Funnels for accessing my self-hosted ...
<https://www.xda-developers.com/tailscale-funnel-access-self-hosted-services/>

9 Jun 2025 ... Nobody wants to type in IP addresses or SSH connection details. It's more effort than using SSO to access the service. However, they can, and ...

## 42. (untitled)
</clev?event=StartpageResultClick&sc=2sbbv9Ind9Ew3pgK1XbYe3tyzBvmN3mJ8RvQv1ZdEoQXVrRefzPBHA0o4nod2F6kkviAh4Kb0XBLsUTMDB4cZjNWhWOhcdEF&payload={"bdsSessionId":"0a6b84bb8a634886a566d4eb5d75f2cf","cheqId":"","countryCode":"IL","deviceType":"desktop","endpoint":"search.serp","hasGoogleAds":true,"page_id":"8RULTnqCr7Khn6nq","queryCategory":"web","segment":"startpage.opera","session_id":"WOpCj1IQapRoG7sn","surface":"serp-web","transport":"href-request"}>

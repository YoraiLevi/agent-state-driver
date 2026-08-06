# DuckDuckGo search: tailscale status --json output fields Peer Online ExitNode Tags

## 1. Tailscale CLI · Tailscale Docs
<https://tailscale.com/docs/reference/tailscale-cli>

Get information about exit-nodes in your tailnet. tailscale exit-node .Unlike tailscale status, using this flag gives a detailed list of peers and users in your tailnet that makes it well-suited for automation tasks.

## 2. Network flow logs · Tailscale Docs
<https://tailscale.com/docs/features/logging/network-flow-logs>

January 23, 2026 - User string `json:"user"` // for example, "johndoe@example.com" // Tags are the tags of the node. // It is not populated if the node is owned by a user. Tags []string `json:"tags"` // for example, ["tag:prod","tag:logs"] } The Message.NodeID field is verified by the Tailscale logs service as the actual node from which the message originated.

## 3. Tailscale 101: Complete Developer Reference Guide for Mesh VPN Networking
<https://blog.starmorph.com/blog/tailscale-complete-developer-reference-guide>

February 15, 2026 - Modern alternative to passing options to tailscale up — only updates explicitly specified fields. tailscale set --accept-routes tailscale set --advertise-exit-node tailscale set --hostname myserver tailscale set --ssh · Show state of tailscaled and its connections. tailscale status # Table format tailscale status --json # JSON output tailscale status --active # Active connections only

## 4. Syntax reference for the tailnet policy file · Tailscale Docs
<https://tailscale.com/docs/reference/syntax/policy-file>

8 Apr 2026 ... Tags, tag:, Includes any device with the provided tag. internet access through an exit node, autogroup:internet, Includes devices with ...

## 5. Changelog - Tailscale
<https://tailscale.com/changelog>

tailscale dns query|status command supports --json flag to return JSON output. ... tailscale status --json now shows Tags and PrimaryRoutes for Peers.

## 6. Tailscale Peer Relays
<https://tailscale.com/docs/features/peer-relay>

4 Feb 2026 ... You can also use the --relay-server-static-endpoints flag with the tailscale set command to specify additional static endpoints to advertise to ...

## 7. tailscale/tailcfg/tailcfg.go at main - GitHub
<https://github.com/tailscale/tailscale/blob/main/tailcfg/tailcfg.go>

//go:generate go run tailscale.com/cmd/viewer --type=User,Node,Hostinfo,NetInfo,Login,DNSConfig,RegisterResponse,RegisterResponseAuth,RegisterRequest ...

## 8. OAuth Credentials (Trust Credentials) for Tailscale connection
<https://forum.netgate.com/topic/199968/oauth-credentials-trust-credentials-for-tailscale-connection/32?page=1>

22 Jan 2026 ... In Tailscale admin → Machines: node should be online with tag:pfsense ... --json > "$TS_JSON" 2>/dev/null return $? } get_backend_state ...

## 9. Tailscale on AWS: The Gotchas Nobody Warns You About - yaw
<https://yaw.sh/blog/tailscale-aws-practical-guide-gotchas/>

11 Apr 2026 ... Your EC2 instance is now on your tailnet, accessible via Tailscale SSH, tagged for ACL purposes, and named my-app in MagicDNS. Let us break down ...

## 10. ipn package - tailscale.com/ipn - Go Packages
<https://pkg.go.dev/tailscale.com/ipn>

ExitNodeLocalIPError is returned when the requested IP address for an exit node belongs to the local machine. func (ExitNodeLocalIPError) Error ¶ added in v1.

## 11. Connection types · Tailscale Docs
<https://tailscale.com/docs/reference/connection-types>

1 Jun 2026 ... How Tailscale establishes connections · If NAT traversal succeeds, device-a and device-b establish a direct (peer-to-peer) connection. · If the ...

## 12. ipnstate package - tailscale.com/ipn/ipnstate - Go Packages
<https://pkg.go.dev/tailscale.com/ipn/ipnstate>

HaveNodeKey bool `json:",omitempty"` AuthURL string // current URL provided by control to authorize client TailscaleIPs []netip.Addr // Tailscale IP(s) assigned to this node Self *PeerStatus // ExitNodeStatus describes the current exit node. // If nil, an exit node is not in use. ExitNodeStatus *ExitNodeStatus `json:"ExitNodeStatus,omitempty"` // Health contains health check problems. // Empty means everything is good. (or at least that no known // problems are detected) Health []string // This field is the legacy name of CurrentTailnet.MagicDNSSuffix.

## 13. cmd/tailscale/cli: build a mechanism to change the output from `--json` logs in the future · Issue #17619 · tailscale/tailscale
<https://github.com/tailscale/tailscale/issues/17619>

October 23, 2025 - The problem We have CLI commands that print their output in JSON if you use --json (e.g. tailscale status, tailscale lock status). Because --json is a boolean flag, this means we're stuck with ...

## 14. Integrate local Tailscale status output with NetAlertX · jokob-sk/NetAlertX · Discussion #1270
<https://github.com/jokob-sk/NetAlertX/discussions/1270>

Hi, I’d like to integrate my local Tailscale network information with NetAlertX using the command: tailscale status --json | jq -r ' (["devMac","devName","devOwner","devType","devVendor","devFavori...

## 15. Peer overview: support folding by tailnet and/or regional locations · Issue #43 · gbraad-cockpit/cockpit-tailscale
<https://github.com/spotsnel/cockpit-tailscale/issues/43>

September 10, 2023 - "nodekey:...": { "ID": "nThpuE4CNTRL", "PublicKey": "nodekey:...", "HostName": "us-atl-wg-108", "DNSName": "us-atl-wg-108.mullvad.ts.net.", "OS": "", "UserID": 26059037925131574, "TailscaleIPs": [ "...", "..." ], "Tags": [ "tag:mullvad-exit-node" ], "Addrs": null, "CurAddr": "", "Relay": "", "RxBytes": 0, "TxBytes": 0, "Created": "2023-05-17T01:32:58.739093963Z", "LastWrite": "0001-01-01T00:00:00Z", "LastSeen": "0001-01-01T00:00:00Z", "LastHandshake": "0001-01-01T00:00:00Z", "Online": true, "ExitNode": false, "ExitNodeOption": true, "Active": false, "PeerAPIURL": null, "InNetworkMap": true, "InMagicSock": true, "InEngine": false, "Location": { "Country": "USA", "CountryCode": "US", "City": "Atlanta, GA", "CityCode": "ATL", "Priority": 1 } }

## 16. FR: Add Exit Node Usage Information to admin UI · Issue #11131 · tailscale/tailscale
<https://github.com/tailscale/tailscale/issues/11131>

February 14, 2024 - I can find this information in part by running tailscale status --json | jq ".ExitNodeStatus", but this requires that I have a vague idea of which device matches the provided ID (if the device I run the command on is configured to use an exit node), making it a clunky solution.

## 17. Exit node option is not being propagated to other nodes · Issue #15225 · tailscale/tailscale
<https://github.com/tailscale/tailscale/issues/15225>

March 6, 2025 - adminuser@bastion-vm:~$ tailscale status --json | jq .Self | grep ExitNode "ExitNode": false, "ExitNodeOption": true, adminuser@bastion-vm:~$ tailscale version 1.80.2 tailscale commit: 62b8bf6a082c4bea1b9e6ee1962c81c6ee5263d3 other commit: 3c35ee9872cbeac18fbf544a96e594ab9e9f05a4 go version: go1.23.5 · Other machines in my tailnet also show it as an option: $ tailscale status --json | jq '.Peer | .[] | select(.HostName == "bastion-vm")' | grep ExitNode "ExitNode": false, "ExitNodeOption": true,

## 18. Mullvad exit nodes · Tailscale Docs
<https://tailscale.com/docs/features/exit-nodes/mullvad-exit-nodes>

January 9, 2026 - tailscale lock status --json | jq '[.FilteredPeers[] | select(.DNSName | contains("mullvad.ts.net")) | {DNSName, NodeKey: .NodeKey}] | sort_by(.DNSName)'

## 19. tailscale up command · Tailscale Docs
<https://tailscale.com/docs/reference/tailscale-cli/up>

January 26, 2026 - --json Output in JSON format.

## 20. Tailscale Funnel · Tailscale Docs
<https://tailscale.com/docs/features/tailscale-funnel>

When you use Tailscale Funnel, the Funnel relay servers show up in your device's list of Tailscale peers. All peers using the command tailscale status --json display.

## 21. FR: A simpler programmatic way to determine if `--accept-routes` is true or false by improving `tailscale status --json` output · Issue #15654 · tailscale/tailscale
<https://github.com/tailscale/tailscale/issues/15654>

April 12, 2025 - Perhaps tailscale set --json or just having tailscale status --json include a "Settings": { .... } object with all the settings, like --accept-routes, in it. Though some things like .ExitNodeStatus are already provided as desired. Supports much easier programmatic detection of if --accept-routes is true or false. Allows me to avoid the brittle workaround of checking for the hardcoded "Some peers are advertising routes but --accept-routes is false" string.

## 22. Status and Preferences JSON | cataphract/tailscale-systray | DeepWiki
<https://deepwiki.com/cataphract/tailscale-systray/5.4-status-and-preferences-json>

The Tailscale CLI outputs structured JSON data that describes the current state of the VPN daemon, connected peers, and user configuration. This data is parsed by TailscaleExec::status() and TailscaleExec::prefs() methods in.

## 23. Complete Tailscale VPN Setup Guide | Demon Warrior Tech Docs
<https://docs.demonwarriortech.com/Documented+Tutorials/VPN/Setting_Up_Tailscale/>

tailscale status --peers. Test connectivity to another device.tailscale status --json | jq '.Self.KeyExpiry'. Renew authentication key. sudo tailscale up --force-reauth.

## 24. FR: tailscale status --routes to show advertised subnet routes · Issue...
<https://github.com/tailscale/tailscale/issues/20692>

The information is present in tailscale status --json as each peer's AllowedIPs, just not surfaced anywhere in the human-readable output. How should we solve this?

## 25. Как создать VPN в Linux с помощью Tailscale
<https://ru.linux-terminal.com/?p=1669>

Перезапустите демон Tailscale, используя следующую команду: sudo tailscale up --advertise-exit-node. Откройте веб-браузер и перейдите на страницу консоли администратора.

## 26. Tailscale VPN - RaspAP Documentation
<https://docs.raspap.com/features-insiders/tailscale/>

tailscale-using-exit-node. Additionally, your device's Tailscale MagicDNS name is also indicated. Tip.sudo tailscale status --json. Check the Tailscale console and CLI output before creating an issue or starting a discussion related to RaspAP's Tailscale plugin.

## 27. Tailscale Commands Cheat Sheet - 35+ Essential... | PocketCmds
<https://pocketcmds.com/commands/tailscale>

$ tailscale up --exit-node=exit-node-name.Status as JSON. $ tailscale status --peers. Show peers only. $ tailscale whois 100.x.y.z.

## 28. Поднимем Tailscale, шаг за шагом
<https://docs-python.ru/other/tailscale-i-headscale/podnimem-tailscale/>

Шаг за шагом поднимем Tailscale на всех нужных серверах, чтобы backup-сервер мог тянуть бэкапы по приватным, зашифрованным туннелям - без NAT-проблем и без ручной настройки WireGuard.

## 29. Tailscale - ArchWiki
<https://wiki.archlinux.org/title/Tailscale>

Install tailscale and reboot your system. It is also possible to run tailscale as a Docker container. This way, one can run multiple exit nodes on a single machine, each with its own tailnet.

## 30. r/Tailscale on Reddit: Is there a way I can tell which exit node I am using from CLI in Linux?
<https://www.reddit.com/r/Tailscale/comments/18dirro/is_there_a_way_i_can_tell_which_exit_node_i_am/>

## 31. r/Tailscale on Reddit: Node online status using API
<https://www.reddit.com/r/Tailscale/comments/134dgrr/node_online_status_using_api/>

## 32. r/Tailscale on Reddit: `tailscale status` Output
<https://www.reddit.com/r/Tailscale/comments/1br15ig/tailscale_status_output/>

## 33. Troubleshooting guide · Tailscale Docs
<https://tailscale.com/kb/1023/troubleshooting>

Troubleshoot common tailnet scenarios.

## 34. Exit nodes (route all traffic) · Tailscale Docs
<https://tailscale.com/kb/1103/exit-nodes>

Route all internet traffic through a specific device on your network.

## 35. Use exit nodes · Tailscale Docs
<https://tailscale.com/kb/1408/quick-guide-exit-nodes>

Route traffic through a specific device in your tailnet, and configure devices to use an exit node.

## 36. r/Tailscale on Reddit: exit node not showing up
<https://www.reddit.com/r/Tailscale/comments/1exuumd/exit_node_not_showing_up/>

## 37. (untitled)
</clev?event=StartpageResultClick&sc=AR5cSbelezF3xAyuC3YyXld0o3lYxtRcg45jvwZlicGpYwbk3Xn4xFc14HEWmPZ3MffJt9ACJ5tMhe0YxdLQwNuJ3TzF6J&payload={"bdsSessionId":"cdd06694d2d2477791644967a29761f9","cheqId":"","countryCode":"IL","deviceType":"desktop","endpoint":"search.serp","hasGoogleAds":true,"page_id":"KOefdYcKCl3LbFid","queryCategory":"web","segment":"startpage.opera","session_id":"12wQgIwfDOVzD15VX","surface":"serp-web","transport":"href-request"}>

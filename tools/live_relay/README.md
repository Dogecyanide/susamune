# Moonshine Timewarp private relay

This server joins two Wiis by a six-digit room code and forwards their live ghost
and race messages. Each Wii initiates its connection; neither home router needs a
port-forward rule. Mario's controls and game simulation stay on the local Wii.

This is an unencrypted private prototype. Room codes are invitations, not passwords.
The server sees UDP peer addresses; a tunnel may present local forwarding
addresses instead. It does not send those addresses to the other console or
write them to a log.
Restarting the server closes its rooms. No database or account system is involved.
Server package 2 keeps listening after UDP peer resets or oversized datagrams;
these errors previously could terminate the Windows relay.
Server package 3 adds optional `--diagnostics` output: aggregate packet and
handshake counts every five seconds, including idle windows. It logs no peer
addresses, room codes, names, nonces, tokens or packet contents. This is enabled
on the organiser's current temporary relay to diagnose the Wii timeout.
Server package 5 accepts protocol 1, 2 and 3 envelopes. Prototypes 9 and 10 use
protocol 3 for recorded Yoshi motion and burst-spray observations; Prototype 8
uses protocol 2 for opponent inputs and draft sets. The two players in a room
must still use the same prototype. Updating this server closes existing rooms;
stop the previous process before starting the new one on the same port.

## Free temporary hosting on your Windows PC

Run the relay on the Dutch tester's PC and expose its one UDP port through
[Playit](https://playit.gg/). Playit currently includes plain **UDP** tunnels on
its free tier; **TCP+UDP** is a separate paid option. Only the host PC needs its
agent. Both Wiis connect normally, without home-router port forwarding.

1. Extract this server ZIP and double-click **start-windows.cmd**. Leave the
   relay window open. It uses Python 3.10 or newer and changes no system settings.
   If the developer already started the relay using your existing Python, skip
   this step; do not start a second copy.
2. Create a free account at [playit.gg](https://playit.gg/) and get the Windows
   agent from its **Download** page. Run it and follow its link to claim the
   agent in your account. Keep the agent running.
3. Create one tunnel for that agent with these settings:

   | Setting | Value |
   | --- | --- |
   | Type | **UDP** |
   | Port count | **1** |
   | Local address | **127.0.0.1** |
   | Local port | **38400** |

4. Send the developer the tunnel's **public IPv4 address and assigned public
   port**. Both Wiis must enter that public pair, including the host's own Wii.
   The public port may differ from 38400. Do not enter `127.0.0.1` on either Wii.
   If Playit shows only a hostname, send it and its port so the developer can
   resolve the numeric IPv4 address for this prototype.
5. Keep the PC awake and both programs running during the test. Closing the
   relay or Playit disconnects the room. Stop both programs when finished.

No home IP address, router password, administrator login or new inbound Windows
firewall rule is needed for this loopback setup. The tunnel uses Playit's network;
it has not been created or verified merely by producing this package.

The first test is **PAL60 in the Netherlands versus Orange's JP game in Japan**.
Free Playit tunnels use global anycast, whose routing can be indirect. Treat the
test as a functional and responsiveness check, then measure the in-game ping and
ghost jitter before judging the best achievable latency. See
[Playit's routing explanation](https://playit.gg/support/playit-premium/).

The Windows script tries `py -3`, then `python`, and checks for Python 3.10+.
The developer can pass an existing Python executable as its first argument.
It installs nothing and binds the relay only to `127.0.0.1:38400`.

## Optional: an existing Linux server

This is an alternative if someone already has a public IPv4 Linux host; renting
one is not required for the first test. It needs Python 3.10+ and permission to
receive UDP 38400 through its provider and operating-system firewalls. A web-only
host or HTTP reverse proxy does not expose this protocol.

Copy this directory to the server, then run:

```sh
python3 --version
python3 server.py --bind 0.0.0.0 --port 38400
```

Leave that terminal running. Its startup message confirms that the local socket
opened; successful console room creation confirms the Internet path works.
If the machine uses UFW, allow the one game port:

```sh
sudo ufw allow 38400/udp comment 'Moonshine private relay'
```

Also allow inbound UDP 38400 in the server provider's firewall. Leave the existing
SSH administration rule in place. Closing the terminal or pressing Ctrl+C stops
the temporary relay and disconnects the room.

## Optional Linux service

The included service runs under a restricted temporary service account. On a
systemd Linux host, install the two files from this directory:

```sh
sudo install -d -m 755 /opt/moonshine-relay
sudo install -m 644 server.py /opt/moonshine-relay/server.py
sudo install -m 644 moonshine-relay.service /etc/systemd/system/moonshine-relay.service
sudo systemctl daemon-reload
sudo systemctl enable --now moonshine-relay
sudo systemctl status moonshine-relay --no-pager
```

The service requires `/usr/bin/python3` to be Python 3.10 or newer. It needs no
third-party packages, file writes, private keys, or application secrets on disk.
The endpoint-challenge secret and room credentials are generated at each startup.

```sh
# Read startup/failure messages.
sudo journalctl -u moonshine-relay --no-pager -n 30
# End the test and prevent automatic startup.
sudo systemctl disable --now moonshine-relay
```

Remove the temporary UDP rule from the provider firewall when the server is no
longer used. For the UFW rule above, use `sudo ufw delete allow 38400/udp`.

## Console flow

1. Both Wiis must pass their normal Wii Internet connection test.
2. Both players use the same Moonshine online prototype and relay address/port.
3. One selects **Create room**, waits for the six-digit code, and shares it with
   the other player. The creator chooses the IL, episode and best-of count.
4. The other enters the code and selects **Join room**. The peer's entered name
   appears after the connection completes. Both players mark themselves ready.
5. The game starts each run locally. The remote runner is a cosmetic live ghost.
   Compare the reported connection delay and visible ghost movement during the
   Netherlands/Japan test; local controller response should remain normal.

An empty room can wait for up to 30 minutes while its creator remains connected.
Paired rooms continue while both consoles stay connected, including long matches.
Loss of either client for 15 seconds closes the room; the inner race connection
may detect a missing peer earlier. Leaving closes a room permanently; if the Wii
retires its outgoing connection before the leave message arrives, the other Wii
detects that departure through the timeout instead. Create
a new room for a reconnect or another match. No replacement player joins an old
round. A fresh endpoint proof retires that console's previous room even if its
leave message was lost, so reconnecting need not wait for the old timeout.
Four-player rooms are outside this prototype.

## Implementation limits

The 48-byte relay envelope carries an existing region-independent `MSR1` packet.
The pose payload is 128 bytes including that envelope: about 3.84 kB/s per sending
console at 30 poses/s, or 4.68 kB/s with IPv4 and UDP headers. Heartbeats, control
messages and network-link overhead add a little more. These are estimates, not a
measured Wii bandwidth result.

An address-bound challenge is required before allocating a room or forwarding
anything. The initial reply is no larger than its request. A successful proof
receives a random 128-bit endpoint token and a random 64-bit room generation.
Forwarded messages carry the recipient's credentials, so peers learn neither the
other console's public address nor its relay token. This authenticates endpoints
against off-path packet injection; it is not encryption or protection against an
attacker who can read the network traffic.

The implementation bounds room/member tables, rate-limit tables, datagram size
and forwarding rates. Current limits are 64 rooms, 256 member records including
recently closed attempts, 1,024 IP rate entries, 60 authenticated packets/s per
member, and a 2,000 packet/s global input budget with short bursts. They are abuse
and memory bounds, not a tested public-service capacity rating. No unbounded
message queues or recording storage are created. The Wii wrapper adds a fixed
small client object and uses the existing bounded transport mailbox.

Focused automated tests in `scripts/test_live_relay.py` run the real C++ relay and
JP/PAL session clients against this Python server. They exercise loss, reordered
readiness, long lobby waits, malformed packets, endpoint proof, terminal rooms,
and rate/capacity limits. They do not replace a real two-Wii Internet test.

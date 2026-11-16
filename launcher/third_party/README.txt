Ghost sharing HTTPS dependencies

BearSSL 0.6, unmodified inc/ and src/ directories, with its MIT license.
Source: https://bearssl.org/bearssl-0.6.tar.gz
Archive SHA-256:
6705bba1714961b41a728dfc5debbe348d2966c117649392f8c8139efc83ff14

Google Trust Services public roots GTS R1, R2, R3 and R4:
https://pki.goog/repo/certs/gtsr1.pem
https://pki.goog/repo/certs/gtsr2.pem
https://pki.goog/repo/certs/gtsr3.pem
https://pki.goog/repo/certs/gtsr4.pem

scripts/generate_ghost_trust_roots.py converts these public certificates into
launcher/kernel/GhostServiceRoots.inc. The generated file records each DER
certificate's SHA-256. No private keys or account credentials are included.

The kernel uses an explicit TLS 1.2 client profile, hostname and date checking,
and IOS58 cryptographic entropy. Unused BearSSL algorithms are discarded by
the linker. The old launcher IOS SSL patching path is not used by this client.

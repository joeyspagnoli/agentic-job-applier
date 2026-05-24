# Tectonic LaTeX engine

This directory ships the prebuilt [tectonic](https://tectonic-typesetting.github.io/) binaries
that the Dockerfile bundles into the runtime image. Tectonic is the
project's only LaTeX engine — `latexmk` and `texlive-full` were dropped
in #61 because tectonic resolves CTAN packages on demand and pulls in
exactly what the active resume templates need.

## Why bundled binaries?

* **No upstream container image.** Tectonic does not publish a container
  to ghcr.io or Docker Hub (verified during issue #61 design). COPYing
  a host-prebuilt tarball is the only reproducible install path.
* **No build-time apt download.** BuildKit DNS to `deb.debian.org` was
  flaky on Docker Desktop for macOS during the #60/#61 work. COPYing a
  tarball that was fetched once over a healthy network sidesteps the
  entire issue.

## Files

| File                    | Target                       | Triple                            |
| ----------------------- | ---------------------------- | --------------------------------- |
| `tectonic-amd64.tar.gz` | `linux/amd64` Docker builds  | `x86_64-unknown-linux-musl`       |
| `tectonic-arm64.tar.gz` | `linux/arm64` Docker builds  | `aarch64-unknown-linux-musl`      |

The Dockerfile selects the right tarball using BuildKit's `TARGETARCH`
argument:

```dockerfile
COPY deploy/tectonic/tectonic-${TARGETARCH}.tar.gz /tmp/tectonic.tar.gz
```

## Refreshing the binaries

When bumping tectonic, run:

```bash
TECTONIC_VERSION=0.15.0 deploy/tectonic/fetch.sh
```

The script downloads both arch tarballs from the
[upstream GitHub release](https://github.com/tectonic-typesetting/tectonic/releases)
and writes them next to itself. Commit the updated tarballs together so
the multi-arch build stays consistent.

After a bump, exercise both arches locally with:

```bash
docker buildx build --platform linux/amd64,linux/arm64 .
```

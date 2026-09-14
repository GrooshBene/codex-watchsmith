# Appended to the release updater's verified-download functions at build time.
def bootstrap_main():
    parser = argparse.ArgumentParser(description='Download a verified Watchsmith release and start interactive setup.')
    parser.add_argument('--version', help='optional stable release tag')
    args = parser.parse_args()
    if sys.version_info < (3, 11):
        print('Install Python 3.11+ and rerun this installer.', file=sys.stderr)
        return 1
    if not sys.stdin.isatty():
        print('Run the downloaded file in an interactive terminal; do not pipe it to Python.', file=sys.stderr)
        return 2
    try:
        data = release(args.version)
        tag = data['tag_name']
        blob = download(asset_url(data, f'codex-watchsmith-{tag}.tar.gz'), MAX_PACKAGE)
        checksum = download(asset_url(data, 'SHA256SUMS'), 4096).decode('ascii')
        with tempfile.TemporaryDirectory(prefix='watchsmith-setup-') as directory:
            source, digest = unpack(blob, checksum, tag, Path(directory))
            if not (source / 'bin/watchsmith_setup.py').is_file():
                raise ValueError('this release has no setup wizard; follow its README')
            env = dict(os.environ, WATCHSMITH_PACKAGE_SHA256=digest)
            return subprocess.call([sys.executable, str(source / 'bin/watchsmith_setup.py'), 'setup'], env=env)
    except (OSError, ValueError, KeyError, TypeError, tarfile.TarError) as error:
        print('Bootstrap failed; no unverified installer was executed. ' + type(error).__name__, file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(bootstrap_main())

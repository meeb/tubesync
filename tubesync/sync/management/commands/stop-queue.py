import difflib
import subprocess
from django.core.management.base import BaseCommand, CommandError
from django_huey import DJANGO_HUEY
from common.logger import log

def find_best_match(query: str, candidates: list[str]) -> str | None:
    """
    Finds the single best match among candidates by looking for trailing suffix
    using endswith, falling back to a sequence distance matching algorithm for typos.
    """
    q = query.strip().lower()

    # 1. Suffix check (allows 'limited' to match 'huey-net-limited')
    for candidate in candidates:
        if candidate.lower().endswith(q):
            return candidate

    # 2. Sequence distance fallback for typos
    candidates_lower = tuple(map(str.lower, candidates))
    matches = difflib.get_close_matches(q, candidates_lower, n=1, cutoff=0.5)
    if matches:
        matched_idx = candidates_lower.index(matches[0])
        return candidates[matched_idx]

    return None

class Command(BaseCommand):
    help = 'Stops a specific task queue consumer service by mapping the provided input to its service name.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--installed',
            type=str,
            help='The version that is currently installed.',
        )
        parser.add_argument(
            '--latest',
            type=str,
            help='The latest version that was released.',
        )
        parser.add_argument(
            '--name',
            type=str,
            help='The name of the software that was released.',
        )
        parser.add_argument(
            'service_input',
            type=str,
            help='A configuration key name, a backend queue name, or a service name suffix.',
        )

    def handle(self, *args, **options):
        service_input = options['service_input'].strip()
        s6_rc_path = '/command/s6-rc'

        # Populate outdated only when everything was provided
        outdated = {}
        if all((
            options['name'], options['name'].strip(),
            options['installed'], options['installed'].strip(),
            options['latest'], options['latest'].strip(),
        )):
            outdated = dict(
                name=options['name'].strip(),
                installed=options['installed'].strip(),
                latest=options['latest'].strip(),
            )

        # Parse configured Django-Huey settings properties immediately
        configured_queues = DJANGO_HUEY.get('queues', {})
        if not configured_queues:
            msg = 'No configurations found inside the DJANGO_HUEY["queues"] framework settings.'
            log.error(msg)
            raise CommandError(msg)

        valid_queue_keys = list(configured_queues.keys())
        valid_queue_names = [ v.get('name') for v in configured_queues.values() if v.get('name') ]

        # Extract defined service names grouped under the 'huey-consumers' s6 bundle
        try:
            s6_list_proc = subprocess.run(
                [s6_rc_path, '-e', 'list', 'huey-consumers'],
                capture_output=True,
                text=True,
                check=True,
            )
        except FileNotFoundError:
            msg = f'Environment Error: "{s6_rc_path}" could not be located. Ensure this command runs inside the container.'
            log.error(msg)
            raise CommandError(msg)
        except subprocess.CalledProcessError as e:
            msg = f'Failed to fetch bundle service definitions from the s6 subsystem: {e.stderr.strip()}'
            log.error(msg)
            raise CommandError(msg)
        else:
            bundle_services = [ line.strip() for line in s6_list_proc.stdout.splitlines() if line.strip() ]

            matched_service_name = None
            matched_queue_key = None
            matched_queue_name = None

            # Resolve the target service name using cascading key, queue name, and suffix parsing rules
            try:
                # Direct case-sensitive dictionary key lookup path
                queue_config = configured_queues[service_input]
            except KeyError:
                # Backup tracking path for loose casings, names, or full service strings
                fuzzy_key = find_best_match(service_input, valid_queue_keys)
  
                if fuzzy_key and fuzzy_key in configured_queues:
                    matched_queue_key = fuzzy_key
                    matched_queue_name = configured_queues[fuzzy_key].get('name')
                    matched_service_name = find_best_match(matched_queue_name, bundle_services)
                else:
                    matched_service_name = find_best_match(service_input, bundle_services)
                    if matched_service_name:
                        matched_queue_name = find_best_match(matched_service_name, valid_queue_names)
                        if matched_queue_name:
                            for key, config in configured_queues.items():
                                if config.get('name') == matched_queue_name:
                                    matched_queue_key = key
                                    break
            else:
                # Direct lookup path processing on match success
                matched_queue_key = service_input
                matched_queue_name = queue_config.get('name')
                matched_service_name = find_best_match(matched_queue_name, bundle_services)

            # Ensure the pipeline successfully identified a single execution target
            if not matched_service_name:
                msg = (
                    f'Could not resolve the identifier "{service_input}" down to a valid service name. '
                    f'Available service choices: {bundle_services}'
                )
                log.error(msg)
                raise CommandError(msg)

            # Display the resolved dependency resolution trace to the user
            self.stdout.write(
                self.style.WARNING(
                    f'Resolution Pipeline Success:\n'
                    f'  Input Provided:  "{service_input}"\n'
                    f'  Service Name:    "{matched_service_name}"\n'
                    f'  Queue Name:      "{matched_queue_name}"\n'
                    f'  Queue Key:       "{matched_queue_key}"\n'
                    f'Stopping service...'
                )
            )

            # Stop the resolved target service name
            log.info('Attempting to stop task queue consumer service "%s"', matched_service_name)

            try:
                result = subprocess.run(
                    [s6_rc_path, '-e', 'stop', matched_service_name],
                    capture_output=True,
                    text=True,
                    check=True,
                )

                log.info('Successfully stopped task queue consumer service "%s"', matched_service_name)

                # Log a high-visibility error alerting the detached environment that tasks are no longer being processed
                log.error('The task queue "%s" has been stopped and will no longer execute tasks.', matched_queue_name)

                self.stdout.write(self.style.SUCCESS(f'Successfully stopped task queue consumer service: "{matched_service_name}".'))
                if result.stdout:
                    self.stdout.write(result.stdout)

            except subprocess.CalledProcessError as e:
                msg = f'The s6-rc subsystem failed to alter the service execution state: {e.stderr.strip()}'
                log.error(msg)
                raise CommandError(msg)

            # Log about the outdated software
            if outdated:
                msg = (
                    'A newer version of %(name)s was released:\n'
                    '\tinstalled version = %(installed)s\n'
                    '\tlatest version = %(latest)s\n'
                )
                log.info(msg % outdated)

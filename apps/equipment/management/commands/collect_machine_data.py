import time

from django.db import DatabaseError, InterfaceError, close_old_connections, connections
from django.core.management.base import BaseCommand, CommandError

from common.db import collect_machine_data, get_machine_polling_intervals


class Command(BaseCommand):
    help = 'Collect PLC snapshots once, or use --watch to follow each machine polling_interval.'

    def add_arguments(self, parser):
        parser.add_argument('--machine-id', type=int)
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument('--watch', action='store_true')
        parser.add_argument('--source-node', type=int)
        parser.add_argument('--destination-node', type=int)

    def handle(self, *args, **options):
        try:
            if options['watch']:
                self.watch(options)
                return
            results = collect_machine_data(
                machine_id=options['machine_id'], dry_run=options['dry_run'],
                source_node=options['source_node'], destination_node=options['destination_node'],
            )
        except KeyboardInterrupt:
            self.stdout.write('Collection stopped.')
            return
        except Exception as error:
            raise CommandError(str(error)) from error
        for result in results:
            self.stdout.write(self.style.SUCCESS(str(result)))

    def watch(self, options):
        last_finished = {}
        self.stdout.write('Polling by machine.polling_interval (seconds). Press Ctrl+C to stop.')
        while True:
            try:
                close_old_connections()
                intervals = get_machine_polling_intervals(options['machine_id'])
            except (DatabaseError, InterfaceError) as error:
                connections['default'].close()
                self.stderr.write('Database unavailable; reconnecting in 5 seconds: {}'.format(error))
                time.sleep(5)
                continue
            last_finished = {key: value for key, value in last_finished.items() if key in intervals}
            for machine_id, interval in intervals.items():
                if machine_id in last_finished and time.monotonic() < last_finished[machine_id] + interval:
                    continue
                try:
                    results = collect_machine_data(
                        machine_id=machine_id, dry_run=options['dry_run'],
                        source_node=options['source_node'], destination_node=options['destination_node'],
                    )
                    for result in results:
                        self.stdout.write(self.style.SUCCESS(str(result)))
                except Exception as error:
                    if isinstance(error, (DatabaseError, InterfaceError)):
                        connections['default'].close()
                    self.stderr.write('Machine {}: {}'.format(machine_id, error))
                finally:
                    last_finished[machine_id] = time.monotonic()
            time.sleep(1)
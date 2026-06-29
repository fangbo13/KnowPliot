# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""Django management command to check and reset the DashScope circuit breaker.

V4.3 UAT: When the circuit breaker is OPEN (e.g., DashScope API key expired,
network connectivity issue), all chat requests return degraded responses.
Use this command to:
- Check the current circuit breaker state
- Reset the circuit breaker to CLOSED (e.g., after fixing DashScope configuration)
- List recent circuit breaker log entries

Usage:
    python manage.py circuitbreaker --check     # Show current state
    python manage.py circuitbreaker --reset     # Force reset to CLOSED
"""

from django.core.management.base import BaseCommand
from apps.core.circuit_breaker import dashscope_breaker


class Command(BaseCommand):
    help = 'Check or reset the DashScope circuit breaker state'

    def add_arguments(self, parser):
        parser.add_argument(
            '--check',
            action='store_true',
            help='Show current circuit breaker state (default)',
        )
        parser.add_argument(
            '--reset',
            action='store_true',
            help='Reset circuit breaker to CLOSED state',
        )

    def handle(self, *args, **options):
        if options['reset']:
            # Force reset the circuit breaker to CLOSED
            with dashscope_breaker._lock:
                old_state = dashscope_breaker._state
                dashscope_breaker._state = dashscope_breaker.CLOSED
                dashscope_breaker._failure_count = 0
                dashscope_breaker._last_failure_time = 0.0
            self.stdout.write(
                self.style.SUCCESS(
                    f'Circuit breaker reset: {old_state} → CLOSED'
                )
            )
        else:
            # Check current state
            state = dashscope_breaker.state
            failure_count = dashscope_breaker._failure_count
            threshold = dashscope_breaker.failure_threshold
            recovery_timeout = dashscope_breaker.recovery_timeout

            state_display = {
                'closed': self.style.SUCCESS('CLOSED ✓'),
                'open': self.style.ERROR('OPEN ✗ (fail-fast)'),
                'half_open': self.style.WARNING('HALF_OPEN ⚠ (probing)'),
            }

            self.stdout.write(f'DashScope Circuit Breaker State: {state_display.get(state, state)}')
            self.stdout.write(f'Failure count: {failure_count}/{threshold}')
            self.stdout.write(f'Recovery timeout: {recovery_timeout}s')

            if state == 'open':
                self.stdout.write(
                    self.style.WARNING(
                        '\nCircuit breaker is OPEN — all DashScope requests are '
                        'fail-fast. Run `python manage.py circuitbreaker --reset` '
                        'to force reset after fixing DashScope configuration.'
                    )
                )
            elif state == 'half_open':
                self.stdout.write(
                    self.style.WARNING(
                        '\nCircuit breaker is HALF_OPEN — one probe request is '
                        'allowed. If it succeeds, the circuit will close.'
                    )
                )

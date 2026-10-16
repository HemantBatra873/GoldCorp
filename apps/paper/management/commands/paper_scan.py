from django.core.management.base import BaseCommand

from apps.paper.models import PaperSession
from apps.paper.services import activate_session, manage_exits_for_session, scan_entries_for_session


class Command(BaseCommand):
    help = "Run paper entry + exit scans synchronously for active sessions (or --all)."

    def add_arguments(self, parser):
        parser.add_argument("--session-id", type=int, default=None)
        parser.add_argument("--activate", action="store_true")
        parser.add_argument("--entries-only", action="store_true")
        parser.add_argument("--exits-only", action="store_true")

    def handle(self, *args, **options):
        qs = PaperSession.objects.all()
        if options["session_id"]:
            qs = qs.filter(pk=options["session_id"])
        else:
            qs = qs.filter(is_active=True)

        sessions = list(qs)
        if not sessions:
            self.stdout.write("No matching sessions. Create one in /paper/settings/.")
            return

        for session in sessions:
            if options["activate"] and not session.is_active:
                activate_session(session, active=True)
            self.stdout.write(f"Session #{session.pk} mode={session.mode}")
            if not options["exits_only"]:
                result = scan_entries_for_session(session)
                self.stdout.write(f"  entries: {result}")
            if not options["entries_only"]:
                result = manage_exits_for_session(session)
                self.stdout.write(f"  exits: {result}")

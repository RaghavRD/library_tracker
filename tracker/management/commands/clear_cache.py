from django.core.management.base import BaseCommand
from tracker.models import UpdateCache, FutureUpdateCache


class Command(BaseCommand):
    help = "Clear all cached library update data to force fresh checks"

    def add_arguments(self, parser):
        parser.add_argument(
            "--type",
            type=str,
            choices=["released", "future", "all"],
            default="all",
            help="Type of cache to clear: released updates, future updates, or all",
        )
        parser.add_argument(
            "--library",
            type=str,
            help="Clear cache for a specific library only (e.g., 'tensorflow')",
        )
        parser.add_argument(
            "--confirm",
            action="store_true",
            help="Confirm deletion without prompting",
        )

    def handle(self, *args, **options):
        cache_type = options["type"]
        library_name = options.get("library")
        auto_confirm = options["confirm"]

        # Count records before deletion
        released_count = UpdateCache.objects.count()
        future_count = FutureUpdateCache.objects.count()

        if library_name:
            released_count = UpdateCache.objects.filter(library__icontains=library_name).count()
            future_count = FutureUpdateCache.objects.filter(library__icontains=library_name).count()

        # Show what will be deleted
        self.stdout.write(self.style.MIGRATE_HEADING("\n🗑️  Cache Clear Utility\n"))
        
        if cache_type in ["released", "all"]:
            self.stdout.write(f"  Released updates cache: {released_count} records")
        if cache_type in ["future", "all"]:
            self.stdout.write(f"  Future updates cache: {future_count} records")
        
        if library_name:
            self.stdout.write(f"  Filter: library contains '{library_name}'")
        
        total = 0
        if cache_type in ["released", "all"]:
            total += released_count
        if cache_type in ["future", "all"]:
            total += future_count

        if total == 0:
            self.stdout.write(self.style.WARNING("\n⚠️  No cache records to delete.\n"))
            return

        # Confirm deletion
        if not auto_confirm:
            self.stdout.write(self.style.WARNING(f"\n⚠️  This will DELETE {total} cache record(s)."))
            confirm = input("Are you sure you want to proceed? [y/N]: ")
            if confirm.lower() != "y":
                self.stdout.write(self.style.ERROR("❌ Cancelled.\n"))
                return

        # Perform deletion
        deleted_released = 0
        deleted_future = 0

        if cache_type in ["released", "all"]:
            if library_name:
                queryset = UpdateCache.objects.filter(library__icontains=library_name)
            else:
                queryset = UpdateCache.objects.all()
            
            deleted_released = queryset.count()
            queryset.delete()

        if cache_type in ["future", "all"]:
            if library_name:
                queryset = FutureUpdateCache.objects.filter(library__icontains=library_name)
            else:
                queryset = FutureUpdateCache.objects.all()
            
            deleted_future = queryset.count()
            queryset.delete()

        # Show results
        self.stdout.write(self.style.SUCCESS(f"\n✅ Cache cleared successfully!\n"))
        if deleted_released > 0:
            self.stdout.write(f"   • Deleted {deleted_released} released update records")
        if deleted_future > 0:
            self.stdout.write(f"   • Deleted {deleted_future} future update records")
        
        self.stdout.write(self.style.SUCCESS("\n💡 Next run_daily_check will fetch fresh data for all libraries.\n"))

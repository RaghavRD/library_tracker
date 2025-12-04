import os
from django.core.management.base import BaseCommand
from tracker.utils.send_mail import send_update_email


class Command(BaseCommand):
    help = "Test the email HTML template with mock data"

    def add_arguments(self, parser):
        parser.add_argument(
            "--save",
            action="store_true",
            help="Save HTML to a file instead of printing to console",
        )
        parser.add_argument(
            "--send",
            action="store_true",
            help="Actually send the email (requires valid Mailtrap credentials)",
        )
        parser.add_argument(
            "--email",
            type=str,
            default="test@example.com",
            help="Email address to send test email to (used with --send)",
        )
        parser.add_argument(
            "--type",
            type=str,
            choices=["single", "multiple", "future"],
            default="single",
            help="Type of email to test: single update, multiple updates, or future update",
        )

    def handle(self, *args, **options):
        email_type = options["type"]
        save_to_file = options["save"]
        send_email = options["send"]
        recipient_email = options["email"]

        # Prepare mock data based on type
        if email_type == "single":
            test_data = self._get_single_update_data()
        elif email_type == "multiple":
            test_data = self._get_multiple_updates_data()
        else:  # future
            test_data = self._get_future_update_data()

        self.stdout.write(self.style.MIGRATE_HEADING(f"\n📧 Testing Email Template ({email_type} update)\n"))

        # Set TEST_MODE based on whether we're sending or not
        original_test_mode = os.getenv("TEST_MODE")
        if send_email:
            os.environ["TEST_MODE"] = "False"
            test_data["recipients"] = recipient_email
            self.stdout.write(self.style.WARNING(f"⚠️  Sending actual email to: {recipient_email}"))
        else:
            os.environ["TEST_MODE"] = "True"

        try:
            # Generate the email
            ok, info = send_update_email(**test_data)

            if send_email:
                if ok:
                    self.stdout.write(self.style.SUCCESS(f"✅ Email sent successfully!"))
                    self.stdout.write(f"   {info}")
                else:
                    self.stdout.write(self.style.ERROR(f"❌ Failed to send email: {info}"))
            else:
                # In test mode, the HTML is printed to console
                # Let's also optionally save it to a file
                if save_to_file:
                    output_file = f"/Users/raghavdesai/Documents/Projects/LibTrack AI/LibTrack_AI_11Nov/test_email_{email_type}.html"
                    
                    # Extract HTML from the payload by regenerating it
                    html_content = self._generate_html(**test_data)
                    
                    with open(output_file, "w", encoding="utf-8") as f:
                        f.write(html_content)
                    
                    self.stdout.write(self.style.SUCCESS(f"\n✅ HTML saved to: {output_file}"))
                    self.stdout.write(f"   Open it in your browser to preview the email!\n")
                else:
                    self.stdout.write(self.style.SUCCESS("\n✅ Email HTML generated (see output above)"))
                    self.stdout.write(f"   Tip: Use --save to save HTML to a file for browser preview\n")

        finally:
            # Restore original TEST_MODE
            if original_test_mode:
                os.environ["TEST_MODE"] = original_test_mode
            elif "TEST_MODE" in os.environ:
                del os.environ["TEST_MODE"]

    def _get_single_update_data(self):
        """Mock data for a single library update"""
        return {
            "mailtrap_api_key": os.getenv("MAILTRAP_MAIN_KEY"),
            "project_name": "AI Model Training Platform",
            "recipients": ["dev@example.com"],
            "library": "tensorflow",
            "version": "2.15.0",
            "category": "major",
            "summary": "Major release with significant performance improvements and new features for tensor operations.",
            "source": "https://github.com/tensorflow/tensorflow/releases/tag/v2.15.0",
            "release_date": "2024-12-01",
            "from_email": os.getenv("MAILTRAP_FROM_EMAIL"),
            "updates": [
                {
                    "library": "tensorflow",
                    "version": "2.15.0",
                    "category": "major",
                    "category_label": "Major",
                    "release_date": "2024-12-01",
                    "summary": "Major release with significant performance improvements and new features for tensor operations. Includes enhanced support for GPU acceleration and optimized memory management.",
                    "source": "https://github.com/tensorflow/tensorflow/releases/tag/v2.15.0",
                    "component_type": "library",
                }
            ],
            "future_opt_in": False,
        }

    def _get_multiple_updates_data(self):
        """Mock data for multiple library updates"""
        return {
            "mailtrap_api_key": os.getenv("MAILTRAP_MAIN_KEY"),
            "project_name": "AI Model Training Platform",
            "recipients": ["dev@example.com"],
            "library": "tensorflow + 2 more",
            "version": "2.15.0 and additional releases",
            "category": "mix",
            "summary": "See release summaries below.",
            "source": "",
            "release_date": "2024-12-01",
            "from_email": os.getenv("MAILTRAP_FROM_EMAIL"),
            "updates": [
                {
                    "library": "tensorflow",
                    "version": "2.15.0",
                    "category": "major",
                    "category_label": "Major",
                    "release_date": "2024-12-01",
                    "summary": "Major release with significant performance improvements and new features.",
                    "source": "https://github.com/tensorflow/tensorflow/releases/tag/v2.15.0",
                    "component_type": "library",
                },
                {
                    "library": "numpy",
                    "version": "1.26.2",
                    "category": "minor",
                    "category_label": "Minor",
                    "release_date": "2024-11-28",
                    "summary": "Bug fixes and minor improvements to array operations.",
                    "source": "https://github.com/numpy/numpy/releases/tag/v1.26.2",
                    "component_type": "library",
                },
                {
                    "library": "python",
                    "version": "3.12.1",
                    "category": "minor",
                    "category_label": "Minor",
                    "release_date": "2024-12-05",
                    "summary": "Security fixes and performance optimizations.",
                    "source": "https://www.python.org/downloads/release/python-3121/",
                    "component_type": "language",
                },
            ],
            "future_opt_in": False,
        }

    def _get_future_update_data(self):
        """Mock data for a future/planned update"""
        return {
            "mailtrap_api_key": os.getenv("MAILTRAP_MAIN_KEY"),
            "project_name": "AI Model Training Platform",
            "recipients": ["dev@example.com"],
            "library": "pytorch",
            "version": "2.2.0",
            "category": "future",
            "summary": "Planned major release with improved CUDA support and new neural network layers. Expected to include significant performance improvements.",
            "source": "https://github.com/pytorch/pytorch/milestone/42",
            "release_date": "Q1 2025",
            "from_email": os.getenv("MAILTRAP_FROM_EMAIL"),
            "updates": [
                {
                    "library": "pytorch",
                    "version": "2.2.0",
                    "category": "future",
                    "category_label": "Future",
                    "release_date": "Q1 2025",
                    "summary": "Planned major release with improved CUDA support and new neural network layers. Expected to include significant performance improvements.",
                    "source": "https://github.com/pytorch/pytorch/milestone/42",
                    "component_type": "library",
                    "confidence": 85,
                }
            ],
            "future_opt_in": True,
        }

    def _generate_html(self, **kwargs):
        """Generate the same HTML that send_update_email would create"""
        updates_payload = kwargs.get("updates", [])
        project_name = kwargs.get("project_name", "")
        future_opt_in = kwargs.get("future_opt_in", False)
        category = kwargs.get("category", "")
        
        has_confidence = any("confidence" in u for u in updates_payload)
        
        table_rows_html = "".join(
            f"""
                <tr>
                    <td style="padding:8px;border:1px solid #dfe3e7;">{entry.get('library', 'Unknown')}</td>
                    <td style="padding:8px;border:1px solid #dfe3e7;">{entry.get('component_type', 'library').title()}</td>
                    <td style="padding:8px;border:1px solid #dfe3e7;">{entry.get('version', 'n/a')}</td>
                    <td style="padding:8px;border:1px solid #dfe3e7;">{entry.get('category_label') or entry.get('category', 'n/a')}</td>
                    <td style="padding:8px;border:1px solid #dfe3e7;">{entry.get('release_date', 'Unknown')}</td>
                    {f'<td style="padding:8px;border:1px solid #dfe3e7;"><strong>{entry.get("confidence", "N/A")}%</strong></td>' if has_confidence else ''}
                </tr>
        """
            for entry in updates_payload
        )

        summary_sections = []
        for entry in updates_payload:
            entry_source = entry.get("source") or ""
            link_html = (
                f"<a href='{entry_source}' target='_blank' rel='noopener'>Read release notes</a>"
                if entry_source
                else "<span style='color:#999'>Source link not provided.</span>"
            )
            summary_sections.append(
                f"""
            <div style="margin:0 0 16px;">
                <p style="margin:0 0 6px;"><strong>{entry.get('library', 'Unknown')} {entry.get('version', '')}</strong></p>
                <p style="margin:0 0 6px;">{entry.get('summary', 'No summary provided.')}</p>
                {link_html}
            </div>
            """
            )

        summary_blocks = "".join(summary_sections) or "<p>No summary details were provided for these releases.</p>"
        
        future_notice_html = ""
        if future_opt_in or category == "future":
            confidences = [u.get("confidence", 0) for u in updates_payload if "confidence" in u]
            avg_confidence = sum(confidences) // len(confidences) if confidences else 0
            
            confidence_text = ""
            if avg_confidence > 0:
                confidence_text = f" (confidence: {avg_confidence}%)"
            
            future_notice_html = f"""
        <div style="margin:16px 0;padding:16px;border:2px solid #f0ad4e;background:#fff8e5;border-radius:4px;">
            <strong style="color:#856404;">⚠️ Future Update Notice{confidence_text}</strong><br/>
            <p style="margin:8px 0 0 0;color:#856404;">
                This is a <strong>planned/upcoming</strong> release that has <strong>NOT been officially released yet</strong>. 
                We detected this based on official announcements or roadmaps. 
                You'll receive another notification when this version is officially released.
            </p>
        </div>
        """

        html_content = f"""
    <div style="font-family:Inter,system-ui,-apple-system,sans-serif;font-size:14px;color:#111;line-height:1.5">
        <p style="margin:0 0 16px;">Hello Team,</p>
        <p style="margin:0 0 16px;">
            LibTrack AI detected {'upcoming planned' if future_opt_in or category == 'future' else 'recent'} update activity 
            impacting the <strong>{project_name}</strong> project.
            Please review the details below and plan follow-up actions as needed.
        </p>
        <table style="width:100%;border-collapse:collapse;font-size:13px;margin:0 0 16px;">
            <thead>
                <tr style="background:#f0f4f8;text-align:left;">
                    <th style="padding:8px;border:1px solid #dfe3e7;">Library</th>
                    <th style="padding:8px;border:1px solid #dfe3e7;">Type</th>
                    <th style="padding:8px;border:1px solid #dfe3e7;">Version</th>
                    <th style="padding:8px;border:1px solid #dfe3e7;">Category</th>
                    <th style="padding:8px;border:1px solid #dfe3e7;">Release Date</th>
                    {f'<th style="padding:8px;border:1px solid #dfe3e7;">Confidence</th>' if has_confidence else ''}
                </tr>
            </thead>
            <tbody>
                {table_rows_html}
            </tbody>
        </table>
        <p style="margin:0 0 12px;"><strong>Release Summary</strong></p>
        {summary_blocks}
        {future_notice_html}
        <p style="margin:16px 0;">
            Kindly schedule upgrades or mitigations as appropriate. as this is automated notification. Do not reply to this message.
        </p>
        <p style="margin:0;">Best regards,<br/><strong>LibTrack AI</strong></p>
        <hr style="margin:24px 0;border:none;border-top:1px solid #e5e7eb;"/>
        <p style="color:#666;font-size:12px;margin:0;">Automated notification powered by LibTrack AI.</p>
    </div>
    """
        
        return html_content

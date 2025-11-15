
<!DOCTYPE html>
<html lang="en">

<head>
    <meta charset="utf-8" />
    <title>LibTrack AI – Register Project</title>
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <!-- Bootstrap via CDN -->
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet" />
</head>

<body>
  <div style="font-family:Inter,system-ui,-apple-system,sans-serif;font-size:14px;color:#111;line-height:1.5">
        <p style="margin:0 0 16px;">Hello Team,</p>
        <p style="margin:0 0 16px;">
            LibTrack AI detected a new <strong>{category.lower()} update</strong> affecting the
            <strong>{library}</strong> dependency in the <strong>{project_name}</strong> project.
            Please review the release details below.
        </p>
        <table style="width:100%;border-collapse:collapse;font-size:13px;margin:0 0 16px;">
            <tbody>
                <tr>
                    <td style="padding:6px 8px;border:1px solid #dfe3e7;background:#f7f9fb;"><strong>Library</strong></td>
                    <td style="padding:6px 8px;border:1px solid #dfe3e7;">{library}</td>
                </tr>
                <tr>
                    <td style="padding:6px 8px;border:1px solid #dfe3e7;background:#f7f9fb;"><strong>Version</strong></td>
                    <td style="padding:6px 8px;border:1px solid #dfe3e7;">{version}</td>
                </tr>
                <tr>
                    <td style="padding:6px 8px;border:1px solid #dfe3e7;background:#f7f9fb;"><strong>Category</strong></td>
                    <td style="padding:6px 8px;border:1px solid #dfe3e7;">{category.title()}</td>
                </tr>
            </tbody>
        </table>
        <p style="margin:0 0 8px;"><strong>Release Summary</strong></p>
        <p style="white-space:pre-wrap;margin:0 0 16px;">{summary}</p>
        {source_block}
        <p style="margin:16px 0;">
            Kindly plan upgrades or mitigations as needed. Reply to this message if you need additional context.
        </p>
        <p style="margin:0;">Best regards,<br/><strong>LibTrack AI</strong></p>
        <hr style="margin:24px 0;border:none;border-top:1px solid #e5e7eb;"/>
        <p style="color:#666;font-size:12px;margin:0;">Automated notification powered by LibTrack AI.</p>
    </div>
  <!-- Bootstrap JS -->
  <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
  {% block extra_scripts %}{% endblock %}
</body>

</html>
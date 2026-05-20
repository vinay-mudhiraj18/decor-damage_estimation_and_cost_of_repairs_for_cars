from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('detection', '0003_detectionreport'),
    ]

    operations = [
        migrations.AddField(
            model_name='detectionreport',
            name='original_image',
            field=models.ImageField(blank=True, null=True, upload_to='reports/original/'),
        ),
        migrations.AddField(
            model_name='detectionreport',
            name='detected_image',
            field=models.ImageField(blank=True, null=True, upload_to='reports/detected/'),
        ),
    ]

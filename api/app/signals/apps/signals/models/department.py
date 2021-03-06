from django.contrib.gis.db import models


class Department(models.Model):
    code = models.CharField(max_length=3)
    name = models.CharField(max_length=255)
    is_intern = models.BooleanField(default=True)

    class Meta:
        permissions = (
            ('sia_department_read', 'Can add/change a department'),
            ('sia_department_write', 'Can add/change a department'),
        )

        ordering = ('name',)
        indexes = [
            models.Index(fields=['name']),
        ]

    def __str__(self):
        """String representation."""
        return '{code} ({name})'.format(code=self.code, name=self.name)

    def active_categorydepartment_set(self):
        return self.categorydepartment_set.filter(category__is_active=True)

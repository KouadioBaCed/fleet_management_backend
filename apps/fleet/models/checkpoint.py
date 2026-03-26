from django.db import models


class MissionCheckpoint(models.Model):
    """Point de passage intermédiaire d'une mission"""

    mission = models.ForeignKey(
        'fleet.Mission',
        on_delete=models.CASCADE,
        related_name='checkpoints',
        verbose_name='Mission'
    )
    order = models.PositiveIntegerField(verbose_name='Ordre')
    address = models.CharField(max_length=255, verbose_name='Adresse')
    latitude = models.DecimalField(
        max_digits=10,
        decimal_places=7,
        verbose_name='Latitude'
    )
    longitude = models.DecimalField(
        max_digits=10,
        decimal_places=7,
        verbose_name='Longitude'
    )
    notes = models.TextField(blank=True, verbose_name='Notes')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Date de création')

    class Meta:
        db_table = 'mission_checkpoints'
        ordering = ['order']
        unique_together = [('mission', 'order')]
        verbose_name = 'Point de passage'
        verbose_name_plural = 'Points de passage'

    def __str__(self):
        return f"{self.mission.mission_code} - Point {self.order}: {self.address}"

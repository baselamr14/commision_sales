from odoo import api, fields, models


class CrmLead(models.Model):
    _inherit = "crm.lead"

    geo_latitude = fields.Float(string="Latitude", digits=(16, 6), tracking=True)
    geo_longitude = fields.Float(string="Longitude", digits=(16, 6), tracking=True)
    geo_accuracy = fields.Float(string="Accuracy (m)", digits=(16, 2), tracking=True)
    geo_location_fetched_at = fields.Datetime(string="Location Fetched At", tracking=True)
    geo_map_url = fields.Char(string="Map URL", compute="_compute_geo_map_url")

    @api.depends("geo_latitude", "geo_longitude")
    def _compute_geo_map_url(self):
        for rec in self:
            if rec.geo_latitude and rec.geo_longitude:
                rec.geo_map_url = (
                    f"https://www.google.com/maps?q={rec.geo_latitude},{rec.geo_longitude}"
                )
            else:
                rec.geo_map_url = False
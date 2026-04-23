/** @odoo-module **/

import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { useService } from "@web/core/utils/hooks";

export class GeoLocationButton extends Component {
    static template = "crm_lead_geolocation.GeoLocationButton";
    static props = {
        ...standardFieldProps,
    };

    setup() {
        this.notification = useService("notification");
        this.orm = useService("orm");
    }

    async reverseGeocode(latitude, longitude) {
        const url =
            `https://nominatim.openstreetmap.org/reverse?format=jsonv2` +
            `&lat=${encodeURIComponent(latitude)}` +
            `&lon=${encodeURIComponent(longitude)}` +
            `&addressdetails=1`;

        const response = await fetch(url, {
            headers: {
                Accept: "application/json",
            },
        });

        if (!response.ok) {
            throw new Error("Reverse geocoding request failed.");
        }

        return await response.json();
    }

    async getCountryId(countryName) {
        if (!countryName) {
            return false;
        }

        const countryIds = await this.orm.search(
            "res.country",
            [["name", "ilike", countryName]],
            { limit: 1 }
        );
        return countryIds.length ? countryIds[0] : false;
    }

    async getStateId(stateName, countryId) {
        if (!stateName || !countryId) {
            return false;
        }

        const stateIds = await this.orm.search(
            "res.country.state",
            [
                ["name", "ilike", stateName],
                ["country_id", "=", countryId],
            ],
            { limit: 1 }
        );
        return stateIds.length ? stateIds[0] : false;
    }

    getFormattedNow() {
        const now = new Date();
        const pad = (n) => String(n).padStart(2, "0");
        return (
            `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())} ` +
            `${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`
        );
    }

    async writeLeadValues(vals) {
    const record = this.props.record;

            if (record.isNew) {
                await record.save();
            }

            const leadId = record.resId || record.data.id;

            if (!leadId) {
                throw new Error("Lead ID not found after save.");
            }

            await this.orm.write("crm.lead", [leadId], vals);
            await record.model.root.load();
        }

    async onClickGetLocation() {
        if (!navigator.geolocation) {
            this.notification.add("Geolocation is not supported on this device/browser.", {
                title: "Location Error",
                type: "danger",
            });
            return;
        }

        navigator.geolocation.getCurrentPosition(
            async (position) => {
                const latitude = position.coords.latitude;
                const longitude = position.coords.longitude;
                const accuracy = position.coords.accuracy || 0;

                let vals = {
                    geo_latitude: latitude,
                    geo_longitude: longitude,
                    geo_accuracy: accuracy,
                    geo_location_fetched_at: this.getFormattedNow(),
                };

                try {
                    const geoData = await this.reverseGeocode(latitude, longitude);
                    const addr = geoData.address || {};

                    const streetParts = [
                        addr.house_number,
                        addr.road || addr.pedestrian || addr.residential,
                    ].filter(Boolean);

                    vals.street = streetParts.join(" ").trim() || false;
                    vals.street2 = addr.suburb || addr.neighbourhood || false;
                    vals.city = addr.city || addr.town || addr.village || false;
                    vals.zip = addr.postcode || false;

                    const countryId = await this.getCountryId(addr.country);
                    if (countryId) {
                        vals.country_id = countryId;
                    }

                    const stateName = addr.state || addr.region || false;
                    const stateId = await this.getStateId(stateName, countryId);
                    if (stateId) {
                        vals.state_id = stateId;
                    }
                } catch (e) {
                    console.warn("Reverse geocoding failed:", e);
                    this.notification.add(
                        "Coordinates were captured, but the address could not be resolved automatically.",
                        {
                            title: "Partial Success",
                            type: "warning",
                        }
                    );
                }

                try {
                    await this.writeLeadValues(vals);

                    this.notification.add("Location captured successfully.", {
                        title: "Success",
                        type: "success",
                    });
                } catch (e) {
                    console.error("Save error:", e);
                    this.notification.add(
                        e?.message || "Could not save location data.",
                        {
                            title: "Save Error",
                            type: "danger",
                        }
                    );
                }
            },
            (error) => {
                let message = "Unable to get your current location.";

                if (error.code === 1) {
                    message = "Location permission was denied.";
                } else if (error.code === 2) {
                    message = "Location information is unavailable.";
                } else if (error.code === 3) {
                    message = "Location request timed out.";
                }

                this.notification.add(message, {
                    title: "Location Error",
                    type: "warning",
                });
            },
            {
                enableHighAccuracy: true,
                timeout: 15000,
                maximumAge: 0,
            }
        );
    }
}

const geoLocationButtonField = {
    component: GeoLocationButton,
    displayName: "Geo Location Button",
    supportedTypes: ["char"],
};

registry.category("fields").add("geo_location_button", geoLocationButtonField);
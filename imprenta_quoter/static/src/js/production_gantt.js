/** @odoo-module **/

import { Component, useState, onWillStart, onWillUpdateProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

class ImprGanttField extends Component {
    static template = "imprenta_quoter.GanttField";
    static props = { ...standardFieldProps };

    setup() {
        this.orm = useService("orm");
        this.state = useState({
            processes: [],
            loading: true,
            minDate: null,
            maxDate: null,
            totalDays: 1,
        });

        onWillStart(() => this._loadData());
        onWillUpdateProps((nextProps) => {
            // Solo recargar si cambia el ID del registro
            if (nextProps.record?.resId !== this.props.record?.resId) {
                this._loadData();
            }
        });
    }

    get productionId() {
        return this.props.record.resId;
    }

    async _loadData() {
        if (!this.productionId) {
            this.state.loading = false;
            return;
        }
        this.state.loading = true;
        try {
            const processes = await this.orm.searchRead(
                "impr.production.process",
                [["production_id", "=", this.productionId], ["active", "=", true]],
                ["name", "date_start", "date_end", "people_required", "state",
                 "sequence", "duration_days", "delay_days"],
                { order: "sequence asc" }
            );
            this.state.processes = processes;
            this._computeScale();
        } finally {
            this.state.loading = false;
        }
    }

    _computeScale() {
        const procs = this.state.processes;
        if (!procs.length) return;

        let minDate = null;
        let maxDate = null;
        for (const p of procs) {
            if (p.date_start) {
                const s = new Date(p.date_start);
                const e = new Date(p.date_end || p.date_start);
                if (!minDate || s < minDate) minDate = s;
                if (!maxDate || e > maxDate) maxDate = e;
            }
        }
        if (minDate && maxDate) {
            this.state.minDate = minDate;
            this.state.maxDate = maxDate;
            this.state.totalDays = Math.max(
                Math.ceil((maxDate - minDate) / 86400000) + 1,
                1
            );
        }
    }

    getBarStyle(process) {
        if (!this.state.minDate || !process.date_start) return "width: 100%;";
        const start = new Date(process.date_start);
        const end = new Date(process.date_end || process.date_start);
        const total = this.state.totalDays;
        const offsetD = Math.ceil((start - this.state.minDate) / 86400000);
        const durD = Math.ceil((end - start) / 86400000) + 1;
        const left = (offsetD / total) * 100;
        const width = Math.max((durD / total) * 100, 5);
        return `left:${left}%;width:${width}%;`;
    }

    getBarClass(process) {
        return `impr-gantt-bar ${process.state}`;
    }

    fmtDate(dateStr) {
        if (!dateStr) return "";
        return new Date(dateStr).toLocaleDateString("es-PE", { day: "2-digit", month: "short" });
    }

    async onMarkDone(processId) {
        await this.orm.call("impr.production.process", "action_mark_done", [processId]);
        await this._loadData();
    }
}

registry.category("fields").add("impr_gantt_widget", {
    component: ImprGanttField,
    supportedTypes: ["one2many"],
});

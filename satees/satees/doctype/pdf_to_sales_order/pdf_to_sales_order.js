// Copyright (c) 2026, Abdul Hasib and contributors
// For license information, please see license.txt


frappe.ui.form.on("Pdf To Sales Order", {
    refresh(frm) { frm.trigger("get_items"); },
    pdf(frm)     { frm.trigger("get_items"); },

    get_items(frm) {
        frm.call({ method: "get_items", doc: frm.doc }).then((r) => {
            if (r.message) frm.events.render_items_table(frm, r.message);
        });
    },

    render_items_table(frm, items) {
        const $wrapper = frm.get_field("item_list").$wrapper;
        $wrapper.empty();
        frm._resolved   = {};
        frm._controls   = {};
        frm._last_items = items;

        if (!document.getElementById("wpdf-lv-styles")) {
            const s = document.createElement("style");
            s.id = "wpdf-lv-styles";
            s.textContent = `
                .wpdf-lv-wrap {
                    width: 100%;
                    overflow-x: auto;
                    border: 1px solid var(--border-color);
                    border-radius: var(--border-radius);
                    background: var(--card-bg);
                    margin-top: 8px;
                }
                .wpdf-lv {
                  
                    border-collapse: collapse;
                    font-size: var(--text-sm);
                    table-layout: fixed;
                }
                /* Column widths */
                .wpdf-lv .wpdf-col-serial   { width: 38px; }
                .wpdf-lv .wpdf-col-so       { width: 150px; }
                .wpdf-lv .wpdf-col-customer { width: 150px; }
                .wpdf-lv .wpdf-col-itemcode { width: 110px; }
                .wpdf-lv .wpdf-col-desc     { width: 150px; }
                .wpdf-lv .wpdf-col-location { width: 140px; }
                .wpdf-lv .wpdf-col-date     { width: 120px; }
                .wpdf-lv .wpdf-col-qty      { width: 70px; }
                .wpdf-lv .wpdf-col-status   { width: 130px; }
                /* Header */
                .wpdf-lv thead th {
                    padding: 9px 10px;
                    font-weight: 600;
                    font-size: var(--text-xs);
                    color: var(--heading-color);
                    white-space: nowrap;
                    background: var(--subtle-fg);
                    border-bottom: 1px solid var(--border-color);
                    text-align: left;
                    overflow: hidden;
                    text-overflow: ellipsis;
                }
                .wpdf-lv thead th.wpdf-col-serial,
                .wpdf-lv thead th.wpdf-col-qty,
                .wpdf-lv thead th.wpdf-col-status { text-align: center; }
                /* Rows */
                .wpdf-lv tbody tr {
                    border-bottom: 1px solid var(--border-color);
                    background: transparent;
                    transition: background 0.1s;
                }
                .wpdf-lv tbody tr:last-child { border-bottom: none; }
                .wpdf-lv tbody tr:hover { background: var(--hover-bg, var(--fg-color)); }
                /* Cells */
                .wpdf-lv tbody td {
                    padding: 7px 10px;
                    vertical-align: top;
                    color: var(--text-color);
                    font-size: var(--text-sm);
                    overflow: hidden;
                }
                .wpdf-lv tbody td.wpdf-col-serial {
                    text-align: center;
                    vertical-align: middle;
                    color: var(--text-muted);
                    font-size: var(--text-xs);
                    padding: 7px 4px;
                }
                .wpdf-lv tbody td.wpdf-col-status {
                    text-align: center;
                    vertical-align: middle;
                }
                .wpdf-lv-desc {
                    white-space: normal;
                    word-break: break-word;
                    overflow-wrap: break-word;
                }
                /* Frappe controls compact */
                .wpdf-ctrl .frappe-control        { margin-bottom: 0 !important; }
                .wpdf-ctrl .form-group            { margin-bottom: 0 !important; }
                .wpdf-ctrl .control-label         { display: none !important; }
                .wpdf-ctrl .help-box              { display: none !important; }
                .wpdf-ctrl .input-with-feedback   { margin-bottom: 0 !important; }
                .wpdf-ctrl input, .wpdf-ctrl .form-control { font-size: var(--text-xs) !important; }
                .wpdf-ctrl .invalid { border-color: var(--border-color) !important; }
                /* Plain SO input */
                .wpdf-so-plain {
                    width: 100%;
                    box-sizing: border-box;
                    font-size: var(--text-xs) !important;
                }
                /* Hint */
                .wpdf-hint {
                    font-size: var(--text-xs);
                    color: var(--red-500);
                    margin-top: 3px;
                    display: block;
                    line-height: 1.4;
                }
                /* SO status alert */
                .wpdf-so-alert {
                    display: flex;
                    align-items: flex-start;
                    gap: 5px;
                    margin-top: 4px;
                    padding: 4px 7px;
                    border-radius: var(--border-radius-sm);
                    font-size: var(--text-xs);
                    line-height: 1.4;
                    border: 1px solid var(--border-color);
                    background: var(--subtle-fg);
                }
                .wpdf-so-alert-icon { flex-shrink: 0; }
                /* Add New button */
                .wpdf-add-btn { margin-top: 5px; font-size: var(--text-xs); }
                /* Create item wrap + disabled overlay */
                .wpdf-create-wrap { position: relative; display: block; }
                .wpdf-disabled-overlay {
                    position: absolute;
                    inset: 0;
                    cursor: not-allowed;
                    z-index: 1;
                }
                /* Popover */
                .wpdf-popover {
                    position: absolute;
                    bottom: calc(100% + 6px);
                    left: 50%;
                    transform: translateX(-50%);
                    background: var(--card-bg);
                    border: 1px solid var(--border-color);
                    border-radius: var(--border-radius);
                    box-shadow: 0 4px 16px rgba(0,0,0,.12);
                    padding: 10px 14px;
                    min-width: 200px;
                    z-index: 200;
                    font-size: var(--text-xs);
                    color: var(--text-color);
                    line-height: 1.5;
                    white-space: normal;
                }
                .wpdf-popover::after {
                    content: "";
                    position: absolute;
                    top: 100%; left: 50%;
                    transform: translateX(-50%);
                    border: 6px solid transparent;
                    border-top-color: var(--border-color);
                }
                .wpdf-popover-title {
                    font-weight: 600;
                    margin-bottom: 6px;
                    color: var(--heading-color);
                }
                .wpdf-popover-row {
                    display: flex; align-items: center;
                    gap: 7px; padding: 2px 0;
                }
                .wpdf-dot {
                    width: 7px; height: 7px; border-radius: 50%;
                    flex-shrink: 0; background: var(--red-500);
                }
                .wpdf-dot-ok { background: var(--green-500); }
            `;
            document.head.appendChild(s);
        }

        // ── Table skeleton ────────────────────────────────────────────────
        const $wrap  = $(`<div class="wpdf-lv-wrap"></div>`);
        const $table = $(`<table class="wpdf-lv"></table>`);
        const $thead = $(`<thead><tr>
            <th class="wpdf-col-serial">#</th>
            <th class="wpdf-col-so">${__("SO No")}</th>
            <th class="wpdf-col-customer">${__("Customer")}</th>
            <th class="wpdf-col-itemcode">${__("Item Code")}</th>
            <th class="wpdf-col-desc">${__("Description")}</th>
            <th class="wpdf-col-location">${__("Location")}</th>
            <th class="wpdf-col-date">${__("Delivery Date")}</th>
            <th class="wpdf-col-qty">${__("Qty")}</th>
            <th class="wpdf-col-status">${__("Status")}</th>
        </tr></thead>`);
        const $tbody = $(`<tbody></tbody>`);
        $table.append($thead).append($tbody);

        // ── Helpers ───────────────────────────────────────────────────────
        function make_ctrl(df, parent_el) {
            return frappe.ui.form.make_control({
                df: Object.assign({ label: "" }, df),
                parent: parent_el,
                render_input: true,
            });
        }

        function link_cell(opts) {
            const $td   = $(`<td class="${opts.col_class || ""}"></td>`);
            const $ctrl = $(`<div class="wpdf-ctrl"></div>`);
            const ctrl  = make_ctrl({
                fieldtype:   "Link",
                fieldname:   opts.fieldname,
                options:     opts.doctype,
                read_only:   opts.read_only ? 1 : 0,
                placeholder: opts.read_only ? "" : __("Search…"),
            }, $ctrl[0]);
            ctrl.set_value(opts.value || "");
            if (!opts.read_only && opts.on_change) {
                ctrl.$input.on("change", () => opts.on_change(ctrl.get_value()));
            }
            if (opts.hint) $td.append(`<span class="wpdf-hint">${opts.hint}</span>`);
            $td.append($ctrl);
            if (opts.add_new_label) {
                const $btn = $(`<button class="btn btn-xs btn-default wpdf-add-btn">${opts.add_new_label}</button>`);
                $btn.on("click", opts.add_new_click);
                $td.append($btn);
            }
            return { $td, ctrl };
        }

        // ── Show/update SO alert badge ────────────────────────────────────
        function set_so_alert($alert, found, val) {
            if (!val) { $alert.hide().empty(); return; }
            if (found) {
                $alert.html(`
                    <span class="wpdf-so-alert-icon" style="color:var(--green-500)">✓</span>
                    <span style="color:var(--green-500)">${__("Found in system")}</span>
                `).css({
                    background: "var(--green-50, var(--subtle-fg))",
                    borderColor: "var(--green-200, var(--border-color))",
                    color: "var(--green-500)",
                }).show();
            } else {
                $alert.html(`
                    <span class="wpdf-so-alert-icon" style="color:var(--orange-500,var(--yellow-500))">⚠</span>
                    <span>${__("Not in system — SO will be created")}</span>
                `).css({
                    background: "var(--yellow-50, var(--subtle-fg))",
                    borderColor: "var(--yellow-200, var(--border-color))",
                    color: "var(--text-color)",
                }).show();
            }
        }

        // ── Render rows ───────────────────────────────────────────────────
        items.forEach((item) => {
            const seq = item.seq;

            // _resolved tracks live user edits for this row
            frm._resolved[seq] = {
                so_no:         item.so_no        || "",
                so_exists:     item.so_exists     || false,   // ← track live
                customer_id:   item.customer_id  || "",
                location:      (item.location && item.location !== "Not Found") ? item.location : "",
                delivery_date: item.delivery_date || "",
                qty:           item.qty           || "",
            };
            frm._controls[seq] = {};

            const $tr = $(`<tr data-seq="${seq}"></tr>`);

            // ── Serial ────────────────────────────────────────────────────
            $tr.append(`<td class="wpdf-col-serial">${seq}</td>`);

            // ── SO No ─────────────────────────────────────────────────────
            const $so_td = $(`<td class="wpdf-col-so"></td>`);

            if (item.so_exists) {
                // Exists → read-only link
                const $c = $(`<div class="wpdf-ctrl"></div>`);
                const c  = make_ctrl({ fieldtype:"Link", fieldname:`so_${seq}`, options:"Sales Order", read_only:1 }, $c[0]);
                c.set_value(item.so_no);
                $so_td.append($c);
            } else {
                // Not in system → plain text input + live status badge
                const $input = $(`
                    <input type="text"
                        class="form-control form-control-sm wpdf-so-plain"
                        data-seq="${seq}"
                        value="${(item.so_no || "").replace(/"/g,"&quot;")}"
                        placeholder="${__("Enter SO ID…")}">
                `);
                const $alert = $(`<div class="wpdf-so-alert" style="display:none;"></div>`);

                // Initial state: SO came from PDF but not found
                if (item.so_no) {
                    set_so_alert($alert, false, item.so_no);
                }

                $input.on("input", function () {
                    const val = $(this).val().trim();
                    frm._resolved[seq].so_no = val;
                    if (!val) {
                        frm._resolved[seq].so_exists = false;
                        $alert.hide().empty();
                        return;
                    }
                    clearTimeout($(this).data("_t"));
                    $(this).data("_t", setTimeout(() => {
                        frappe.call({
                            method: "frappe.client.get_value",
                            args: { doctype:"Sales Order", filters:{ name: val }, fieldname:"name" },
                            callback(r) {
                                const found = !!(r.message && r.message.name);
                                // Update resolved so_exists live
                                frm._resolved[seq].so_exists = found;
                                set_so_alert($alert, found, val);
                            },
                        });
                    }, 500));
                });

                $so_td.append($input).append($alert);
            }
            $tr.append($so_td);

            // ── Customer ──────────────────────────────────────────────────
            const { $td: $cust_td, ctrl: cust_ctrl } = link_cell({
                col_class: "wpdf-col-customer",
                fieldname: `cust_${seq}`, doctype: "Customer",
                value:         item.customer_found ? (item.customer_id || item.customer) : "",
                read_only:     item.customer_found,
                hint:          !item.customer_found && item.customer ? item.customer : null,
                on_change:     (v) => { frm._resolved[seq].customer_id = v; },
                add_new_label: !item.customer_found ? __("+ Add New") : null,
                add_new_click: !item.customer_found ? () => {
                    const name = item.customer || "";
                    localStorage.setItem("wpdf_pending", JSON.stringify({
                        docname: frm.doc.name, type: "customer", prefill: { customer_name: name },
                    }));
                    frappe.ui.form.on("Customer", { refresh(f) {
                        if (!f.is_new()) return;
                        f.set_value("customer_name", name);
                        frappe.ui.form.off("Customer", "refresh");
                    }});
                    frappe.set_route("Form", "Customer", "new-customer-1");
                } : null,
            });
            if (!item.customer_found) frm._controls[seq].customer = cust_ctrl;
            $tr.append($cust_td);

            // ── Item Code & Description ───────────────────────────────────
            $tr.append(`<td class="wpdf-col-itemcode" style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${item.item_code || ""}</td>`);
            $tr.append(`<td class="wpdf-col-desc wpdf-lv-desc">${item.description || ""}</td>`);

            // ── Location ──────────────────────────────────────────────────
            const loc_found = item.location && item.location !== "Not Found";
            const { $td: $loc_td, ctrl: loc_ctrl } = link_cell({
                col_class: "wpdf-col-location",
                fieldname: `loc_${seq}`, doctype: "Warehouse",
                value:         loc_found ? item.location : "",
                read_only:     loc_found,
                hint:          !loc_found && item.raw_location ? item.raw_location : null,
                on_change:     (v) => {
                    frm._resolved[seq].location = v;
                    frm.events.refresh_create_btn(frm, seq);
                },
                add_new_label: !loc_found ? __("+ Add New") : null,
                add_new_click: !loc_found ? () => {
                    const loc = item.raw_location || "";
                    localStorage.setItem("wpdf_pending", JSON.stringify({
                        docname: frm.doc.name, type: "warehouse", prefill: { warehouse_name: loc },
                    }));
                    frappe.ui.form.on("Warehouse", { refresh(f) {
                        if (!f.is_new()) return;
                        f.set_value("warehouse_name", loc);
                        frappe.ui.form.off("Warehouse", "refresh");
                    }});
                    frappe.set_route("Form", "Warehouse", "new-warehouse-1");
                } : null,
            });
            if (!loc_found) frm._controls[seq].location = loc_ctrl;
            $tr.append($loc_td);

            // ── Delivery Date ─────────────────────────────────────────────
            const $date_td   = $(`<td class="wpdf-col-date"></td>`);
            const $date_ctrl = $(`<div class="wpdf-ctrl"></div>`);
            const date_ctrl  = make_ctrl({
                fieldtype: "Date", fieldname: `date_${seq}`,
                read_only: item.delivery_date ? 1 : 0,
            }, $date_ctrl[0]);
            date_ctrl.set_value(item.delivery_date || "");
            if (!item.delivery_date) {
                const $hint = $(`<span class="wpdf-hint">${__("⚠ Required")}</span>`);
                $date_td.append($hint);
                date_ctrl.$input.on("change", () => {
                    const val = date_ctrl.get_value();
                    frm._resolved[seq].delivery_date = val;
                    val ? $hint.hide() : $hint.show();
                    frm.events.refresh_create_btn(frm, seq);
                });
                frm._controls[seq].date = date_ctrl;
            }
            $date_td.append($date_ctrl);
            $tr.append($date_td);

            // ── Qty ───────────────────────────────────────────────────────
            const has_qty   = item.qty && String(item.qty).trim() !== "";
            const $qty_td   = $(`<td class="wpdf-col-qty"></td>`);
            const $qty_ctrl = $(`<div class="wpdf-ctrl"></div>`);
            const qty_ctrl  = make_ctrl({
                fieldtype: "Float", fieldname: `qty_${seq}`,
                read_only: has_qty ? 1 : 0,
            }, $qty_ctrl[0]);
            qty_ctrl.set_value(has_qty ? item.qty : "");
            if (!has_qty) {
                const $hint = $(`<span class="wpdf-hint">${__("⚠ Required")}</span>`);
                $qty_td.append($hint);
                qty_ctrl.$input.on("change", () => {
                    const v = parseFloat(qty_ctrl.get_value());
                    const ok = !isNaN(v) && v > 0;
                    frm._resolved[seq].qty = ok ? v : "";
                    ok ? $hint.hide() : $hint.show();
                    frm.events.refresh_create_btn(frm, seq);
                });
                frm._controls[seq].qty = qty_ctrl;
            }
            $qty_td.append($qty_ctrl);
            $tr.append($qty_td);

            // ── Status ────────────────────────────────────────────────────
            const $stat_td = $(`<td class="wpdf-col-status"></td>`);
            if (item.status === "Found") {
                $stat_td.append(`<span class="indicator-pill green" style="font-size:var(--text-xs);">${__("Found")}</span>`);
            } else {
                const safe_code  = (item.item_code || "").replace(/"/g, "&quot;");
                const safe_desc  = (item.description || item.item_code || "").replace(/"/g, "&quot;");
                const r          = frm._resolved[seq];
                const can_create = !!(r.location && r.delivery_date && r.qty);

                const $missing = $(`<div style="margin-bottom:5px;">
                    <span class="indicator-pill red" style="font-size:var(--text-xs);">${__("Missing")}</span>
                </div>`);

                const $create_wrap = $(`<div class="wpdf-create-wrap"></div>`);
                const $btn = $(`
                    <button class="btn btn-default btn-xs create-item-btn"
                        data-seq="${seq}"
                        data-item-code="${safe_code}"
                        data-description="${safe_desc}"
                        style="font-size:var(--text-xs);padding:3px 8px;width:100%;white-space:nowrap;"
                        ${can_create ? "" : "disabled"}>
                        + ${__("Create Item")}
                    </button>`);

                if (!can_create) {
                    const $overlay = $(`<div class="wpdf-disabled-overlay"></div>`);
                    $overlay.on("click", function (e) {
                        e.stopPropagation();
                        const $existing = $create_wrap.find(".wpdf-popover");
                        if ($existing.length) { $existing.remove(); return; }
                        $create_wrap.append(frm.events._make_popover(frm, seq));
                        setTimeout(() => {
                            $(document).one("click.wpdf_pop", () => $create_wrap.find(".wpdf-popover").remove());
                        }, 10);
                    });
                    $create_wrap.append($overlay);
                }

                $create_wrap.append($btn);
                $stat_td.append($missing).append($create_wrap);
            }

            $tr.append($stat_td);
            $tbody.append($tr);
        });

        $wrap.append($table);
        $wrapper.append($wrap);
    },

    // Build popover DOM (reused by overlay click and refresh)
    _make_popover(frm, seq) {
        const r = frm._resolved[seq] || {};
        const fields = [
            { label: __("Location"),      ok: !!r.location },
            { label: __("Delivery Date"), ok: !!r.delivery_date },
            { label: __("Qty"),           ok: !!r.qty },
        ];
        const rows = fields.map(f => `
            <div class="wpdf-popover-row">
                <span class="wpdf-dot ${f.ok ? "wpdf-dot-ok" : ""}"></span>
                <span style="font-size:var(--text-xs);">${f.label}:&nbsp;${f.ok
                    ? `<strong style="color:var(--green-500)">✓</strong>`
                    : `<strong style="color:var(--red-500)">${__("Missing")}</strong>`
                }</span>
            </div>`).join("");
        return $(`<div class="wpdf-popover">
            <div class="wpdf-popover-title">${__("Complete these first")}</div>
            ${rows}
        </div>`);
    },

    refresh_create_btn(frm, seq) {
        const r   = frm._resolved[seq] || {};
        const ok  = !!(r.location && r.delivery_date && r.qty);
        const $td = frm.get_field("item_list").$wrapper.find(`tr[data-seq="${seq}"] .wpdf-col-status`);
        const $btn = $td.find(".create-item-btn");
        $btn.prop("disabled", !ok);
        // Refresh live popover content if open
        const $pop = $td.find(".wpdf-popover");
        if ($pop.length) $pop.replaceWith(frm.events._make_popover(frm, seq));
        if (ok) {
            $td.find(".wpdf-disabled-overlay").remove();
            $td.find(".wpdf-popover").remove();
        }
    },
});


// ── Router ────────────────────────────────────────────────────────────────
frappe.router.on("change", () => {
    const pending = localStorage.getItem("wpdf_pending");
    if (!pending) return;
    let ctx;
    try { ctx = JSON.parse(pending); } catch (e) { return; }
    const route = frappe.get_route();
    if (!route) return;

    if (route[0] === "Form" && route[1] === "Pdf To Sales Order" && route[2] === ctx.docname) {
        localStorage.removeItem("wpdf_pending");
        setTimeout(() => {
            if (cur_frm && cur_frm.doctype === "Pdf To Sales Order") cur_frm.trigger("get_items");
        }, 600);
        return;
    }

    if (route[0] === "Form" && ["Customer", "Item", "Warehouse"].includes(route[1])) {
        const doctype = route[1];
        frappe.ui.form.on(doctype, {
            after_save(inner_frm) {
                const still = localStorage.getItem("wpdf_pending");
                if (!still) return;
                let c;
                try { c = JSON.parse(still); } catch (e) { return; }
                if (inner_frm.is_new() || inner_frm.doc.__unsaved === 1) return;

                if (doctype === "Item" && c.type === "item") {
                    const item_row = Object.assign({}, c.item_row || {}, { item_code: inner_frm.doc.name });
                    localStorage.removeItem("wpdf_pending");
                    frappe.show_alert({ message: __("Item created. Updating Sales Order…"), indicator: "blue" });
                    frappe.call({
                        method: "satees.satees.doctype.pdf_to_sales_order.pdf_to_sales_order.handle_so_after_item",
                        args: {
                            docname:          c.docname,
                            so_no:            c.so_no,
                            so_exists:        c.so_exists ? 1 : 0,
                            item_row:         JSON.stringify(item_row),
                            customer_id:      c.customer_id   || "",
                            customer_name:    c.customer_name || "",
                           
                        },
                        callback(r) {
                            if (r.message && r.message.status === "ok") {
                                frappe.show_alert({
                                    message: r.message.so_exists
                                        ? __("Item added to ") + r.message.so_no
                                        : __("Sales Order created: ") + r.message.so_no,
                                    indicator: "green",
                                });
                            } else {
                                frappe.msgprint({
                                    title:     __("Sales Order Update Failed"),
                                    indicator: "red",
                                    message:   (r.message && r.message.error) || __("Unknown error occurred"),
                                });
                            }
                            frappe.set_route("Form", "Pdf To Sales Order", c.docname);
                        },
                        error(err) {
                            frappe.msgprint({
                                title:     __("Error"),
                                indicator: "red",
                                message:   err.responseJSON && err.responseJSON.exc
                                    ? err.responseJSON.exc
                                    : __("Failed to update Sales Order. Please try again."),
                            });
                            frappe.set_route("Form", "Pdf To Sales Order", c.docname);
                        },
                    });
                } else {
                    localStorage.removeItem("wpdf_pending");
                    frappe.show_alert({ message: __("Returning to PDF form…"), indicator: "blue" });
                    frappe.set_route("Form", "Pdf To Sales Order", c.docname);
                }
            },
        });
    }
});


// ── Create Item click ─────────────────────────────────────────────────────
$(document).on("click", ".create-item-btn:not([disabled])", function () {
    if (!cur_frm || cur_frm.doctype !== "Pdf To Sales Order") return;
    const $btn      = $(this);
    const seq       = $btn.data("seq");
    const item_code = $btn.data("item-code");
    const item_desc = $btn.data("description") || item_code;
    const resolved  = cur_frm._resolved[seq]   || {};
    const row_data  = (cur_frm._last_items || []).find(i => i.seq == seq) || {};

    // so_exists: use live resolved value (updated when user types in plain input)
    const so_no     = resolved.so_no    || row_data.so_no    || "";
    const so_exists = resolved.so_exists !== undefined
        ? resolved.so_exists
        : (row_data.so_exists || false);

    // delivery_date for transaction_date on the new SO
    const delivery_date = resolved.delivery_date || row_data.delivery_date || "";

    localStorage.setItem("wpdf_pending", JSON.stringify({
        docname:          cur_frm.doc.name,
        type:             "item",
        seq,
        so_no,
        so_exists,
        transaction_date: delivery_date,   // used as SO transaction_date in Python
        item_row: {
            item_code,
            qty:           resolved.qty      || row_data.qty      || 1,
            delivery_date: delivery_date,
            warehouse:     resolved.location || "",
        },
        customer_id:   resolved.customer_id   || row_data.customer_id   || "",
        customer_name: row_data.customer      || "",
        prefill:       { item_code, item_name: item_desc },
    }));

    frappe.ui.form.on("Item", {
        refresh(f) {
            if (!f.is_new()) return;
            f.set_value("item_code", item_code);
            f.set_value("item_name", item_desc || item_code);
            frappe.ui.form.off("Item", "refresh");
        },
    });
    frappe.set_route("Form", "Item", "new-item-1");
});
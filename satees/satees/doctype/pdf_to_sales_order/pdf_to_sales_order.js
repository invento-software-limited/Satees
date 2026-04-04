// Copyright (c) 2026, Abdul Hasib and contributors
// For license information, please see license.txt


frappe.ui.form.on("Pdf To Sales Order", {
    refresh(frm) {
        frm.add_custom_button(__("Update Sales Orders"), () => {
            frappe.confirm(__("Update Sales Orders for all valid rows?"), () => {
                // Step 1: Re-validate lookups against DB
                frm.call({ method: "revalidate_lookups", doc: frm.doc }).then((r) => {
                    if (r.message) {
                        frm.events.render_items_table(frm, r.message);
                        // Step 2: Create/Update Sales Orders from updated data
                        frm.call({ method: "create_sales_orders", doc: frm.doc }).then((r2) => {
                            if (r2.message) {
                                frappe.msgprint({
                                    title: __("Update Results"),
                                    message: r2.message.replace(/\n/g, "<br>"),
                                    indicator: "green"
                                });
                            }
                        });
                    }
                });
            });
        }, __("Actions"));

        frm.add_custom_button(__("Refresh Lookups"), () => {
            frm.call({ method: "revalidate_lookups", doc: frm.doc }).then((r) => {
                if (r.message) frm.events.render_items_table(frm, r.message);
            });
        }, __("Actions"));

        frm.add_custom_button(__("Reread PDF"), () => {
            frm.trigger("get_items");
        }, __("Actions"));

        if (frm.doc.pdf_data) {
            try {
                const items = typeof frm.doc.pdf_data === "string" ? JSON.parse(frm.doc.pdf_data) : frm.doc.pdf_data;
                if (items && items.length > 0) {
                    frm.events.render_items_table(frm, items);
                } else if (frm.doc.pdf) {
                    frm.get_field("item_list").$wrapper.html("<div class='alert alert-danger' style='padding: 10px; margin-bottom: 0px; color: var(--red-500, #dc3545); font-weight: bold;'>Please add a valid pdf to create Sales Order.</div>");
                }
            } catch (e) {
                console.error("Failed to parse pdf_data:");
            }
        } else if (frm.doc.pdf) {
            frm.get_field("item_list").$wrapper.html("<div class='alert alert-danger' style='padding: 10px; margin-bottom: 0px; color: var(--red-500, #dc3545); font-weight: bold;'>Please add a valid pdf to create Sales Order.</div>");
        }

        // ── Auto-return logic ─────────────────────────────────────────────
        const pending = localStorage.getItem("wpdf_pending");
        if (pending) {
            const data = JSON.parse(pending);
            if (data.docname === frm.doc.name) {
                localStorage.removeItem("wpdf_pending");
                // Chain the update: Revalidate first, then Create/Update SOs
                frappe.show_alert({ message: __("Updating Sales Orders..."), indicator: "blue" });
                
                frm.call({ method: "revalidate_lookups", doc: frm.doc }).then((r) => {
                    if (r.message) {
                        frm.events.render_items_table(frm, r.message);
                        frm.call({ method: "create_sales_orders", doc: frm.doc }).then((r2) => {
                            if (r2.message) {
                                frappe.msgprint({
                                    title: __("System Updated"),
                                    message: r2.message.replace(/\n/g, "<br>"),
                                    indicator: "green"
                                });
                            }
                        });
                    }
                });
            }
        }
    },

    get_items(frm) {
        frm.call({ method: "get_items", doc: frm.doc }).then((r) => {
            if (r.message && r.message.length > 0) {
                frm.events.render_items_table(frm, r.message);
            } else {
                frm.get_field("item_list").$wrapper.html("<div class='alert alert-danger' style='padding: 10px; margin-bottom: 0px; color: var(--red-500, #dc3545); font-weight: bold;'>Please add a valid pdf to create Sales Order.</div>");
            }
        });
    },

    render_items_table(frm, items) {
        const $wrapper = frm.get_field("item_list").$wrapper;
        $wrapper.empty();
        frm._resolved = {};
        frm._controls = {};
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
                .wpdf-lv .wpdf-col-customer { width: 180px; }
                .wpdf-lv .wpdf-col-itemcode { width: 180px; }
                .wpdf-lv .wpdf-col-desc     { width: 220px; }
                .wpdf-lv .wpdf-col-location { width: 150px; }
                .wpdf-lv .wpdf-col-date     { width: 120px; }
                .wpdf-lv .wpdf-col-qty      { width: 70px; }
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
                .wpdf-lv thead th.wpdf-col-qty { text-align: center; }
                /* Rows */
                .wpdf-lv tbody tr {
                    border-bottom: 1px solid var(--border-color);
                    background: transparent;
                    transition: background 0.1s;
                }
                .wpdf-lv tbody tr:last-child { border-bottom: none; }
                .wpdf-lv tbody tr:hover { background: var(--hover-bg, var(--fg-color)); }
                .wpdf-lv tbody tr:focus-within {
                    z-index: 10;
                    position: relative;
                }
                /* Cells */
                .wpdf-lv tbody td {
                    padding: 7px 10px;
                    vertical-align: top;
                    color: var(--text-color);
                    font-size: var(--text-sm);
                    overflow: visible;
                }
                .wpdf-lv tbody td.wpdf-col-serial {
                    text-align: center;
                    vertical-align: middle;
                    color: var(--text-muted);
                    font-size: var(--text-xs);
                    padding: 7px 4px;
                }
                .wpdf-lv-desc {
                    white-space: normal;
                    word-break: break-word;
                    overflow-wrap: break-word;
                }
                /* Frappe controls compact */
                .wpdf-ctrl {
                    position: relative;
                }
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
        const $wrap = $(`<div class="wpdf-lv-wrap"></div>`);
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
            const $td = $(`<td class="${opts.col_class || ""}"></td>`);
            const $ctrl = $(`<div class="wpdf-ctrl"></div>`);

            let $hint = null;
            if (opts.hint) {
                $hint = $(`<span class="wpdf-hint">${opts.hint}</span>`);
                $td.append($hint);
            }

            let $btn = null;
            let initialized = false;

            const ctrl = make_ctrl({
                fieldtype: "Link",
                fieldname: opts.fieldname,
                options: opts.doctype,
                read_only: opts.read_only ? 1 : 0,
                placeholder: opts.read_only ? "" : __("Search…"),
                change: function () {
                    if (!initialized) return;
                    const val = this.get_value();
                    if (val && $hint) $hint.hide();
                    else if (!val && $hint) $hint.show();

                    if ($btn) {
                        if (val) $btn.hide();
                        else $btn.show();
                    }

                    if (opts.on_change) opts.on_change(val);
                }
            }, $ctrl[0]);

            ctrl.set_value(opts.value || "");
            setTimeout(() => { initialized = true; }, 100);
            $td.append($ctrl);

            if (opts.add_new_label) {
                $btn = $(`<button class="btn btn-xs btn-default wpdf-add-btn">${opts.add_new_label}</button>`);
                $btn.on("click", opts.add_new_click);
                if (opts.value) $btn.hide();
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
                so_no: item.so_no || "",
                so_exists: item.so_exists || false,
                customer_id: item.customer_id || "",
                item_code: item.item_found ? item.item_code : "",
                location: (item.location && item.location !== "Not Found") ? item.location : "",
                delivery_date: item.delivery_date || "",
                qty: item.qty || "",
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
                const c = make_ctrl({ fieldtype: "Link", fieldname: `so_${seq}`, options: "Sales Order", read_only: 1 }, $c[0]);
                c.set_value(item.so_no);
                $so_td.append($c);
            } else {
                // Not in system → plain text input + live status badge
                const $input = $(`
                    <input type="text"
                        class="form-control form-control-sm wpdf-so-plain"
                        data-seq="${seq}"
                        value="${(item.so_no || "").replace(/"/g, "&quot;")}"
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
                            args: { doctype: "Sales Order", filters: { name: val }, fieldname: "name" },
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
                value: item.customer_id || "",
                read_only: 0,
                hint: !item.customer_found && item.customer ? item.customer : null,
                on_change: (v) => {
                    frm._resolved[seq].customer_id = v;
                    const itm = (frm._last_items || []).find(i => i.seq == seq);
                    if (itm) {
                        itm.customer_id = v;
                        itm.customer_found = !!v;
                        if (v) itm.customer = v;
                        frm.set_value("pdf_data", JSON.stringify(frm._last_items));
                        frm.dirty();
                    }
                },
                add_new_label: !item.customer_found ? __("+ Add New") : null,
                add_new_click: () => {
                    const res = frm._resolved[seq] || {};
                    const name = item.customer || "";
                    localStorage.setItem("wpdf_pending", JSON.stringify({
                        docname: frm.doc.name,
                        type: "customer",
                        seq: seq,
                        so_no: res.so_no,
                        so_exists: res.so_exists,
                        customer_id: res.customer_id,
                        customer_name: name,
                        item_row: {
                            item_code: item.item_code || "",
                            qty: res.qty || item.qty || 1,
                            delivery_date: res.delivery_date || item.delivery_date || "",
                            warehouse: res.location || (item.location !== "Not Found" ? item.location : ""),
                        },
                        prefill: { customer_name: name },
                    }));
                    frappe.ui.form.on("Customer", {
                        refresh(f) {
                            if (!f.is_new()) return;
                            f.set_value("customer_name", name);
                            frappe.ui.form.off("Customer", "refresh");
                        },
                        after_save(f) {
                            frappe.set_route("Form", "Pdf To Sales Order", frm.doc.name);
                            frappe.ui.form.off("Customer", "after_save");
                        }
                    });
                    frappe.set_route("Form", "Customer", "new-customer-1");
                }
            });
            $tr.append($cust_td);

            // ── Item Code ──────────────────────────────────────────────────
            const { $td: $item_td, ctrl: item_ctrl } = link_cell({
                col_class: "wpdf-col-itemcode",
                fieldname: `item_${seq}`, doctype: "Item",
                value: item.item_found ? item.item_code : "",
                read_only: item.item_found,
                hint: !item.item_found && item.item_code ? item.item_code : null,
                on_change: (v) => {
                  
                    frm._resolved[seq].item_code = v;
                    const itm = (frm._last_items || []).find(i => i.seq == seq);
                    if (itm) {
                        itm.item_code = v;
                        itm.item_found = !!v;
                        frm.set_value("pdf_data", JSON.stringify(frm._last_items));
                        frm.dirty();
                      
                    }
                    frm.events.refresh_create_btn(frm, seq);
                },
                add_new_label: !item.item_found ? __("+ Add New") : null,
                add_new_click: () => {
                    const res = frm._resolved[seq] || {};
                    const code = item.item_code || "";
                    const desc = item.description || "";
                    localStorage.setItem("wpdf_pending", JSON.stringify({
                        docname: frm.doc.name,
                        type: "item",
                        seq: seq,
                        so_no: res.so_no,
                        so_exists: res.so_exists,
                        customer_id: res.customer_id,
                        customer_name: item.customer || "",
                        item_row: {
                            item_code: code,
                            qty: res.qty || item.qty || 1,
                            delivery_date: res.delivery_date || item.delivery_date || "",
                            warehouse: res.location || (item.location !== "Not Found" ? item.location : ""),
                        },
                        prefill: { item_code: code, item_name: desc },
                    }));
                    frappe.ui.form.on("Item", {
                        refresh(f) {
                            if (!f.is_new()) return;
                            f.set_value("item_code", code);
                            f.set_value("item_name", desc);
                            frappe.ui.form.off("Item", "refresh");
                        },
                        after_save(f) {
                            frappe.set_route("Form", "Pdf To Sales Order", frm.doc.name);
                            frappe.ui.form.off("Item", "after_save");
                        }
                    });
                    frappe.set_route("Form", "Item", "new-item-1");
                }
            });
            if (!item.item_found) frm._controls[seq].item = item_ctrl;
            $tr.append($item_td);

            // ── Description ───────────────────────────────────────────────
            $tr.append(`<td class="wpdf-col-desc wpdf-lv-desc">${item.description || ""}</td>`);

            // ── Location ──────────────────────────────────────────────────
            const loc_found = item.location && item.location !== "Not Found";
            const { $td: $loc_td, ctrl: loc_ctrl } = link_cell({
                col_class: "wpdf-col-location",
                fieldname: `loc_${seq}`, doctype: "Warehouse",
                value: loc_found ? item.location : "",
                read_only: loc_found,
                hint: !loc_found && item.raw_location ? item.raw_location : null,
                on_change: (v) => {
                    frm._resolved[seq].location = v;
                    const itm = (frm._last_items || []).find(i => i.seq == seq);
                    if (itm) {
                        itm.location = v;
                        itm.location_found = !!v;
                        itm.raw_location = v; // Synchronize raw_location for revalidation stability
                        frm.set_value("pdf_data", JSON.stringify(frm._last_items));
                        frm.dirty();
                       
                    }
                    frm.events.refresh_create_btn(frm, seq);
                },
                add_new_label: !loc_found ? __("+ Add New") : null,
                add_new_click: () => {
                    const res = frm._resolved[seq] || {};
                    const loc = item.raw_location || "";
                    localStorage.setItem("wpdf_pending", JSON.stringify({
                        docname: frm.doc.name,
                        type: "warehouse",
                        seq: seq,
                        so_no: res.so_no,
                        so_exists: res.so_exists,
                        customer_id: res.customer_id,
                        customer_name: item.customer || "",
                        item_row: {
                            item_code: item.item_code || "",
                            qty: res.qty || item.qty || 1,
                            delivery_date: res.delivery_date || item.delivery_date || "",
                            warehouse: res.location || (item.location !== "Not Found" ? item.location : ""),
                        },
                        prefill: { warehouse_name: loc },
                    }));
                    frappe.ui.form.on("Warehouse", {
                        refresh(f) {
                            if (!f.is_new()) return;
                            f.set_value("warehouse_name", loc);
                            frappe.ui.form.off("Warehouse", "refresh");
                        },
                        after_save(f) {
                            frappe.set_route("Form", "Pdf To Sales Order", frm.doc.name);
                            frappe.ui.form.off("Warehouse", "after_save");
                        }
                    });
                    frappe.set_route("Form", "Warehouse", "new-warehouse-1");
                }
            });
            if (!loc_found) frm._controls[seq].location = loc_ctrl;
            $tr.append($loc_td);

            // ── Delivery Date ─────────────────────────────────────────────
            const $date_td = $(`<td class="wpdf-col-date"></td>`);
            const $date_ctrl = $(`<div class="wpdf-ctrl"></div>`);
            const date_ctrl = make_ctrl({
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
            const has_qty = item.qty && String(item.qty).trim() !== "";
            const $qty_td = $(`<td class="wpdf-col-qty"></td>`);
            const $qty_ctrl = $(`<div class="wpdf-ctrl"></div>`);
            const qty_ctrl = make_ctrl({
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

            $tbody.append($tr);
        });

        $wrap.append($table);
        $wrapper.append($wrap);
    },

    // Build popover DOM (reused by overlay click and refresh)
    refresh_create_btn(frm, seq) {
        // No-op - Action column removed
    },
});





// ── Create Item click ─────────────────────────────────────────────────────
$(document).on("click", ".create-item-btn:not([disabled])", function () {
    if (!cur_frm || cur_frm.doctype !== "Pdf To Sales Order") return;
    const $btn = $(this);
    const seq = $btn.data("seq");
    const item_code = $btn.data("item-code");
    const item_desc = $btn.data("description") || item_code;
    const resolved = cur_frm._resolved[seq] || {};
    const row_data = (cur_frm._last_items || []).find(i => i.seq == seq) || {};

    // so_exists: use live resolved value (updated when user types in plain input)
    const so_no = resolved.so_no || row_data.so_no || "";
    const so_exists = resolved.so_exists !== undefined
        ? resolved.so_exists
        : (row_data.so_exists || false);

    // delivery_date for transaction_date on the new SO
    const delivery_date = resolved.delivery_date || row_data.delivery_date || "";

    localStorage.setItem("wpdf_pending", JSON.stringify({
        docname: cur_frm.doc.name,
        type: "item",
        seq,
        so_no,
        so_exists,
        transaction_date: delivery_date,   // used as SO transaction_date in Python
        item_row: {
            item_code,
            qty: resolved.qty || row_data.qty || 1,
            delivery_date: delivery_date,
            warehouse: resolved.location || "",
        },
        customer_id: resolved.customer_id || row_data.customer_id || "",
        customer_name: row_data.customer || "",
        prefill: { item_code, item_name: item_desc },
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

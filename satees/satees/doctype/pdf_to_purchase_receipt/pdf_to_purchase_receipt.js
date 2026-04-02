// Copyright (c) 2026, Abdul Hasib and contributors
// For license information, please see license.txt

frappe.ui.form.on("PDF to Purchase Receipt", {
	refresh(frm) {
		if (frm.doc.pdf_data) {
			try {
				const items = typeof frm.doc.pdf_data === "string" ? JSON.parse(frm.doc.pdf_data) : frm.doc.pdf_data;
				if (items && items.length > 0) {
					frm.events.render_items_table(frm, items);
				} else {
					const $wrapper = frm.get_field("item_list").$wrapper;
					$wrapper.html(`<div style="padding:12px; color: var(--red-500);">No items found in PDF. Please check the error log.</div>`);
				}
			} catch (e) {
				console.error("Failed to parse pdf_data:", e);
			}
		} else {
			frm.get_field("item_list").$wrapper.empty();
		}
	},
	supplier_delivery_pdf(frm) {
		if (frm.doc.supplier_delivery_pdf) {
			frm.save();
		}
	},

	get_items(frm) {
		if (!frm.doc.supplier_delivery_pdf) return;

		frappe.show_alert({ message: __("Parsing PDF..."), indicator: "blue" });
		frm.call({ method: "extract_pdf_data", doc: frm.doc }).then((r) => {
			if (r.message && r.message.length > 0) {
				frm.events.render_items_table(frm, r.message);
				frm.reload_doc();
			} else {
				const $wrapper = frm.get_field("item_list").$wrapper;
				$wrapper.html(`<div style="padding:12px; color: var(--red-500);">No items found in PDF. Please check the error log.</div>`);
			}
		});
	},

	render_items_table(frm, items) {
		const $wrapper = frm.get_field("item_list").$wrapper;
		$wrapper.empty();

		if (items.length > 0) {
			const supplierName = items[0].supplier;
			const supplierStatus = items[0].supplier_status;
			
			if (supplierStatus === "Not Found") {
				$wrapper.append(`
					<div style="margin-bottom: 12px; padding: 10px 15px; background: #fde8e8; border: 1px solid #f5c6cb; border-radius: 4px; color: #c0392b; font-size: 13px; display: flex; justify-content: space-between; align-items: center;">
						<div>
							<strong>Warning:</strong> The supplier <strong>${supplierName}</strong> extracted from the PDF was not found in the system. 
							Please create this supplier before creating items or Purchase Receipts.
						</div>
						<button class="btn btn-xs btn-danger wpr-create-supplier-btn" data-supplier="${(supplierName || "").replace(/"/g, "&quot;")}">
							${__("Create Supplier")}
						</button>
					</div>
				`);
			} else {
				$wrapper.append(`
					<div style="margin-bottom: 12px; padding: 10px 15px; background: #d4f7e3; border: 1px solid #a3e9c4; border-radius: 4px; color: #1a7f3c; font-size: 13px;">
						<strong>Supplier Found:</strong> ${supplierName}
					</div>
				`);
			}
		}

		if (!document.getElementById("wpr-lv-styles")) {
			const s = document.createElement("style");
			s.id = "wpr-lv-styles";
			s.textContent = `
				.wpr-lv-wrap { width: 100%; overflow-x: auto; border: 1px solid var(--border-color); border-radius: var(--border-radius); background: var(--card-bg); margin-top: 4px; }
				.wpr-lv { width: 100%; border-collapse: collapse; font-size: var(--text-sm); }
				.wpr-lv thead th { padding: 8px 10px; font-weight: 600; font-size: var(--text-xs); color: var(--heading-color); background: var(--subtle-fg); border-bottom: 2px solid var(--border-color); text-align: left; white-space: nowrap; }
				.wpr-lv tbody td { padding: 7px 10px; vertical-align: middle; border-bottom: 1px solid var(--border-color); color: var(--text-color); font-size: var(--text-sm); }
				.wpr-lv tbody tr:hover { background: rgba(0,0,0,0.02); }
				.wpr-lv tbody tr:last-child td { border-bottom: none; }
				.status-pill { display: inline-block; padding: 2px 10px; border-radius: 20px; font-size: var(--text-xs); font-weight: 600; }
				.status-found { color: #1a7f3c; background-color: #d4f7e3; border: 1px solid #a3e9c4; }
				.status-missing { color: #c0392b; background-color: #fde8e8; border: 1px solid #f5c6cb; }
				.wpr-create-btn { margin-top: 5px; display: block; width: 100%; font-size: var(--text-xs); }
			`;
			document.head.appendChild(s);
		}

		const $wrap = $(`<div class="wpr-lv-wrap"></div>`);
		const $table = $(`<table class="wpr-lv"></table>`);
		const $thead = $(`
			<thead>
				<tr>
					<th style="width:40px;">#</th>
					<th style="width:130px;">${__("Item Code")}</th>
					<th style="width:180px;">${__("Description")}</th>
					<th style="width:60px; text-align:right;">${__("Qty")}</th>
					<th style="width:60px;">${__("UOM")}</th>
					<th style="width:100px;">${__("Batch")}</th>
					<th style="width:120px;">${__("Remarks")}</th>
					<th style="width:130px;">${__("Delivery Order")}</th>
					<th style="width:150px;">${__("Purchase Receipt")}</th>
					<th style="width:110px; text-align:center;">${__("Status")}</th>
				</tr>
			</thead>
		`);
		const $tbody = $(`<tbody></tbody>`);

		items.forEach((item) => {
			const is_found = item.status === "Found";
			const status_class = is_found ? "status-found" : "status-missing";

			const create_btn = !is_found ? `
				<button class="btn btn-xs btn-primary wpr-create-btn"
					data-item-code="${(item.item_code || "").replace(/"/g, "&quot;")}"
					data-desc="${(item.description || "").replace(/"/g, "&quot;")}"
					data-uom="${item.uom || ""}"
					data-do-no="${item.do_no || ""}"
					data-qty="${item.qty || 1}"
					data-batch="${(item.batch || "").replace(/"/g, "&quot;")}"
					data-supplier="${(item.supplier || "").replace(/"/g, "&quot;")}">
					${__("Create")}
				</button>` : "";

			const $tr = $(`
				<tr>
					<td>${item.no || ""}</td>
					<td><strong>${item.item_code || ""}</strong></td>
					<td>${item.description || ""}</td>
					<td style="text-align:right;">${item.qty || ""}</td>
					<td>${item.uom || ""}</td>
					<td>${item.batch || ""}</td>
					<td>${item.remarks || ""}</td>
					<td>${item.do_no || ""}</td>
					<td>${item.pr_name || "-"}</td>
					<td style="text-align:center;">
						<span class="status-pill ${status_class}">${__(item.status)}</span>
						${create_btn}
						<button class="btn btn-xs btn-default wpr-link-btn"
							style="margin-top: 5px; display: block; width: 100%; color: var(--text-muted); border-color: var(--border-color);"
							data-no="${item.no || ""}"
							data-item-code="${(item.item_code || "").replace(/"/g, "&quot;")}">
							${__("Link Item")}
						</button>
					</td>
				</tr>
			`);
			$tbody.append($tr);
		});

		$table.append($thead).append($tbody);
		$wrap.append($table);
		$wrapper.append($wrap);

		// Handle Create button clicks
		$wrap.on("click", ".wpr-create-btn", function() {
			const $btn = $(this);
			const item_code = $btn.data("item-code");
			const desc = $btn.data("desc");
			const uom = $btn.data("uom");
			const do_no = $btn.data("do-no");
			const qty = $btn.data("qty");
			const batch = $btn.data("batch");
			const supplier = $btn.data("supplier");

			localStorage.setItem("wpr_pending", JSON.stringify({
				docname: frm.doc.name,
				item_code,
				uom,
				do_no,
				qty,
				batch,
				supplier
			}));

			frappe.ui.form.on("Item", {
				refresh(f) {
					if (f.is_new()) {
						f.set_value("item_code", item_code);
						f.set_value("item_name", desc || item_code);
						if (uom) f.set_value("stock_uom", uom);
						if (batch) f.set_value("has_batch_no", 1);
					}
					frappe.ui.form.off("Item", "refresh");
				}
			});
			frappe.set_route("Form", "Item", "new-item-1");
		});

		// Handle Create Supplier button
		$wrapper.on("click", ".wpr-create-supplier-btn", function() {
			const $btn = $(this);
			const supplier_name = $btn.data("supplier");

			localStorage.setItem("wpr_pending_supplier", JSON.stringify({
				docname: frm.doc.name,
				supplier_name: supplier_name
			}));

			frappe.ui.form.on("Supplier", {
				refresh(f) {
					if (f.is_new()) {
						f.set_value("supplier_name", supplier_name);
					}
					frappe.ui.form.off("Supplier", "refresh");
				}
			});
			frappe.set_route("Form", "Supplier", "new-supplier-1");
		});

		// Handle Link Item button
		$wrap.on("click", ".wpr-link-btn", function() {
			const $btn = $(this);
			const item_no = $btn.data("no");

			frappe.prompt([
				{
					label: __("Select Existing Item"),
					fieldname: "item_code",
					fieldtype: "Link",
					options: "Item",
					reqd: 1
				}
			], (values) => {
				if (frm.doc.pdf_data) {
					try {
						let data = JSON.parse(frm.doc.pdf_data);
						let item_updated = false;
						data.forEach(d => {
							if (String(d.no) === String(item_no)) {
								d.item_code = values.item_code;
								d.status = "Found";
								item_updated = true;
							}
						});
						if (item_updated) {
							frm.set_value("pdf_data", JSON.stringify(data));
							frm.trigger("render_items_table", data);
							
							frappe.show_alert({ message: __("Linking item and updating Purchase Receipt..."), indicator: "blue" });
							frm.call("sync_pr").then(() => {
								frappe.show_alert({ message: __("Purchase Receipt synchronized."), indicator: "green" });
								frm.reload_doc();
							});
						}
					} catch(e) {
						console.error("Failed to update item link:", e);
					}
				}
			}, __("Link Item to System"), __("Link"));
		});
	}
});

// // Router hook to handle return from Item or Supplier creation
frappe.router.on("change", () => {
	const route = frappe.get_route();
	if (!route) return;

	// Return to the PDF form from Item creation
	const pending = localStorage.getItem("wpr_pending");
	if (pending) {
		let ctx;
		try { ctx = JSON.parse(pending); } catch (e) { return; }

		if (route[0] === "Form" && route[1] === "PDF to Purchase Receipt" && route[2] === ctx.docname) {
			localStorage.removeItem("wpr_pending");
			setTimeout(() => {
				if (cur_frm && cur_frm.doctype === "PDF to Purchase Receipt") {
					cur_frm.reload_doc();
				}
			}, 600);
			return;
		}
	}

	// Return to the PDF form from Supplier creation
	const pending_supplier = localStorage.getItem("wpr_pending_supplier");
	if (pending_supplier) {
		let ctx_supp;
		try { ctx_supp = JSON.parse(pending_supplier); } catch (e) { }

		if (ctx_supp && route[0] === "Form" && route[1] === "PDF to Purchase Receipt" && route[2] === ctx_supp.docname) {
			localStorage.removeItem("wpr_pending_supplier");
			setTimeout(() => {
				if (cur_frm && cur_frm.doctype === "PDF to Purchase Receipt") {
					frappe.show_alert({ message: __("Updating supplier status and synchronizing..."), indicator: "blue" });
					frappe.call({
						method: "satees.satees.doctype.pdf_to_purchase_receipt.pdf_to_purchase_receipt.handle_pr_after_supplier",
						args: {
							docname: cur_frm.doc.name,
							supplier_name: ctx_supp.supplier_name
						},
						callback(r) {
							frappe.show_alert({ message: __("Supplier synchronized."), indicator: "green" });
							cur_frm.reload_doc();
						}
					});
				}
			}, 600);
			return;
		}
	}

	// Attach handlers when on Item or Supplier form
	if (route[0] === "Form" && route[1] === "Item") {
		frappe.ui.form.on("Item", {
			after_save(f) {
				if (localStorage.getItem("wpr_pending")) {
					frappe.show_alert({ message: __("Item created. Updating Purchase Receipt…"), indicator: "blue" });
					let c = JSON.parse(localStorage.getItem("wpr_pending"));
					
					frappe.call({
						method: "satees.satees.doctype.pdf_to_purchase_receipt.pdf_to_purchase_receipt.handle_pr_after_item",
						args: {
							docname: c.docname,
							do_no: c.do_no,
							item_row: JSON.stringify({ item_code: f.doc.name, qty: c.qty, uom: c.uom }),
							supplier_name: c.supplier,
							batch_no: c.batch || "",
							old_item_code: c.item_code
						},
						callback(r) {
							frappe.set_route("Form", "PDF to Purchase Receipt", c.docname);
						}
					});
				}
			}
		});
	}

	if (route[0] === "Form" && route[1] === "Supplier") {
		frappe.ui.form.on("Supplier", {
			after_save(f) {
				const still = localStorage.getItem("wpr_pending_supplier");
				if (still) {
					let c = JSON.parse(still);
					frappe.show_alert({ message: __("Supplier created. Returning to PDF..."), indicator: "green" });
					setTimeout(() => {
						frappe.set_route("Form", "PDF to Purchase Receipt", c.docname);
					}, 800);
				}
			}
		});
	}
});

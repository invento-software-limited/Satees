// Copyright (c) 2026, Abdul Hasib and contributors
// For license information, please see license.txt

frappe.ui.form.on("PDF to Purchase Receipt", {
	refresh(frm) {
		frm.trigger("get_items");
	},
	supplier_delivery_pdf(frm) {
		frm.trigger("get_items");
	},

	get_items(frm) {
		console.log("get_items triggered. Field value:", frm.doc.supplier_delivery_pdf);
		if (!frm.doc.supplier_delivery_pdf) return;

		frappe.show_alert({ message: __("Parsing PDF..."), indicator: "blue" });
		frm.call({ method: "get_items", doc: frm.doc }).then((r) => {
			console.log("get_items response:", r.message);
			if (r.message && r.message.length > 0) {
				frm.events.render_items_table(frm, r.message);
			} else {
				const $wrapper = frm.get_field("item_list").$wrapper;
				$wrapper.html(`<div style="padding:12px; color: var(--red-500);">No items found in PDF. Please check the error log.</div>`);
			}
		});
	},

	render_items_table(frm, items) {
		const $wrapper = frm.get_field("item_list").$wrapper;
		$wrapper.empty();

		if (!document.getElementById("wpr-lv-styles")) {
			const s = document.createElement("style");
			s.id = "wpr-lv-styles";
			s.textContent = `
				.wpr-lv-wrap { width: 100%; overflow-x: auto; border: 1px solid var(--border-color); border-radius: var(--border-radius); background: var(--card-bg); margin-top: 8px; }
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
			const supplier = $btn.data("supplier");

			localStorage.setItem("wpr_pending", JSON.stringify({
				docname: frm.doc.name,
				item_code,
				uom,
				do_no,
				qty,
				supplier
			}));

			frappe.ui.form.on("Item", {
				refresh(f) {
					if (f.is_new()) {
						f.set_value("item_code", item_code);
						f.set_value("item_name", desc || item_code);
						if (uom) f.set_value("stock_uom", uom);
					}
					frappe.ui.form.off("Item", "refresh");
				}
			});
			frappe.set_route("Form", "Item", "new-item-1");
		});
	}
});

// Router hook to handle return from Item creation
frappe.router.on("change", () => {
	const pending = localStorage.getItem("wpr_pending");
	if (!pending) return;

	let ctx;
	try { ctx = JSON.parse(pending); } catch (e) { return; }

	const route = frappe.get_route();
	if (!route) return;

	// Return to the PDF form
	if (route[0] === "Form" && route[1] === "PDF to Purchase Receipt" && route[2] === ctx.docname) {
		localStorage.removeItem("wpr_pending");
		setTimeout(() => {
			if (cur_frm && cur_frm.doctype === "PDF to Purchase Receipt") {
				cur_frm.trigger("get_items");
			}
		}, 600);
		return;
	}

	// When on Item form, listen for save
	if (route[0] === "Form" && route[1] === "Item") {
		frappe.ui.form.on("Item", {
			after_save(f) {
				const still = localStorage.getItem("wpr_pending");
				if (!still) return;
				let c;
				try { c = JSON.parse(still); } catch (e) { return; }

				localStorage.removeItem("wpr_pending");
				frappe.show_alert({ message: __("Item created. Updating Purchase Receipt…"), indicator: "blue" });

				frappe.call({
					method: "satees.satees.doctype.pdf_to_purchase_receipt.pdf_to_purchase_receipt.handle_pr_after_item",
					args: {
						docname: c.docname,
						do_no: c.do_no,
						item_row: JSON.stringify({ item_code: f.doc.name, qty: c.qty }),
						supplier_name: c.supplier
					},
					callback(r) {
						if (r.message && r.message.status === "ok") {
							frappe.show_alert({ message: __("Purchase Receipt updated: ") + r.message.pr_name, indicator: "green" });
						} else if (r.message) {
							frappe.msgprint({ title: __("Error"), indicator: "red", message: r.message.error || __("Unknown error") });
						}
						frappe.set_route("Form", "PDF to Purchase Receipt", c.docname);
					}
				});
			}
		});
	}
});

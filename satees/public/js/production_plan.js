frappe.ui.form.on('Production Plan', {
    on_submit(frm) {
        frm.events.make_work_order(frm);
        frm.events.create_material_request(frm, 1);
    }   
})
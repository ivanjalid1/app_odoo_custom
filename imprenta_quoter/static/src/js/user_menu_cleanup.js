/** @odoo-module **/
/**
 * Limpia el menú de usuario — elimina items innecesarios de Odoo.com
 * Smart Print Quoter
 */
import { registry } from "@web/core/registry";
import { patch } from "@web/core/utils/patch";

const userMenuRegistry = registry.category("user_menuitems");

// Eliminar items que no aplican para uso interno
const toRemove = [
    "documentation",          // Documentación → odoo.com/documentation
    "support",                // Soporte → odoo.com/help
    "odoo_account",           // Mi cuenta de Odoo.com
    "install_pwa",            // Instalar aplicación (PWA)
    "shortcuts",              // Atajos de teclado (CTRL+K)
    "web_tour.tour_enabled",  // Integración / Onboarding (tours guiados)
];

for (const key of toRemove) {
    try {
        userMenuRegistry.remove(key);
    } catch (e) {
        // Si el item no existe, ignorar
    }
}

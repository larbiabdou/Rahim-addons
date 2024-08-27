from odoo import models, fields, api, Command


class MrpBomLine(models.Model):
    _inherit = 'mrp.bom.line'

    calcul_type = fields.Selection([
        ('fixe', 'Fixe'),
        ('hauteur', 'Multiplier par Hauteur'),
        ('largeur', 'Multiplier par Largeur')
    ], string="Type de Calcul", default='fixe')

class StockMove(models.Model):
    _inherit = 'stock.move'

    calcul_type = fields.Selection([
        ('fixe', 'Fixe'),
        ('hauteur', 'Multiplier par Hauteur'),
        ('largeur', 'Multiplier par Largeur')

    ],  related="bom_line_id.calcul_type", string="Type de Calcul", store=True)


class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    hauteur = fields.Float(string="Hauteur", help="Hauteur du produit à fabriquer")
    largeur = fields.Float(string="Largeur", help="Largeur du produit à fabriquer")

    def _get_moves_raw_values(self):
        moves = []
        for production in self:
            if not production.bom_id:
                continue
            factor = production.product_uom_id._compute_quantity(production.product_qty, production.bom_id.product_uom_id) / production.bom_id.product_qty
            boms, lines = production.bom_id.explode(production.product_id, factor, picking_type=production.bom_id.picking_type_id)
            for bom_line, line_data in lines:
                if bom_line.child_bom_id and bom_line.child_bom_id.type == 'phantom' or\
                        bom_line.product_id.type not in ['product', 'consu']:
                    continue
                operation = bom_line.operation_id.id or line_data['parent_line'] and line_data['parent_line'].operation_id.id
                if bom_line.calcul_type == 'hauteur':
                    qty = line_data['qty'] * production.hauteur
                elif bom_line.calcul_type == 'largeur':
                    qty = line_data['qty'] * production.largeur
                else:
                    qty = line_data['qty']
                moves.append(production._get_move_raw_values(
                    bom_line.product_id,
                    qty,
                    bom_line.product_uom_id,
                    operation,
                    bom_line
                ))
        return moves

    @api.depends('company_id', 'bom_id', 'product_id', 'product_qty', 'product_uom_id', 'location_src_id', 'hauteur', 'largeur')
    def _compute_move_raw_ids(self):
        for production in self:
            if production.state != 'draft':
                continue
            list_move_raw = [Command.link(move.id) for move in production.move_raw_ids.filtered(lambda m: not m.bom_line_id)]
            if not production.bom_id and not production._origin.product_id:
                production.move_raw_ids = list_move_raw
            if any(move.bom_line_id.bom_id != production.bom_id or move.bom_line_id._skip_bom_line(production.product_id) \
                   for move in production.move_raw_ids if move.bom_line_id):
                production.move_raw_ids = [Command.clear()]
            if production.bom_id and production.product_id and production.product_qty > 0:
                # keep manual entries
                moves_raw_values = production._get_moves_raw_values()
                move_raw_dict = {move.bom_line_id.id: move for move in production.move_raw_ids.filtered(lambda m: m.bom_line_id)}
                for move_raw_values in moves_raw_values:
                    if move_raw_values['bom_line_id'] in move_raw_dict:
                        # update existing entries
                        list_move_raw += [Command.update(move_raw_dict[move_raw_values['bom_line_id']].id, move_raw_values)]
                    else:
                        # add new entries
                        list_move_raw += [Command.create(move_raw_values)]
                production.move_raw_ids = list_move_raw
            else:
                production.move_raw_ids = [Command.delete(move.id) for move in production.move_raw_ids.filtered(lambda m: m.bom_line_id)]



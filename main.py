from flask import Flask, request, jsonify
from pymongo import MongoClient
from bson import ObjectId
import json
import logging

app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.DEBUG)

# MongoDB Atlas connection
client = MongoClient('mongodb+srv://new-user:OGcenXO5y7QMM10o@atulast.kg8pz.mongodb.net/ruleEngine?retryWrites=true&w=majority')
db = client.ruleEngine
rules_collection = db.rules


# Define Node class for AST representation
class Node:
    def __init__(self, type, value, left=None, right=None):
        self.type = type
        self.value = value
        self.left = left
        self.right = right

    def to_dict(self):
        return {
            'type': self.type,
            'value': self.value,
            'left': self.left.to_dict() if self.left else None,
            'right': self.right.to_dict() if self.right else None
        }

    @classmethod
    def from_dict(cls, data):
        if data is None:
            return None
        return cls(
            type=data['type'],
            value=data['value'],
            left=cls.from_dict(data['left']),
            right=cls.from_dict(data['right'])
        )


# Parse rule string into AST
def parse_rule_string(rule_string):
    tokens = rule_string.replace('(', ' ( ').replace(')', ' ) ').split()

    def parse_expression():
        stack = [[]]
        for token in tokens:
            if token == '(':
                stack.append([])
            elif token == ')':
                expr = stack.pop()
                stack[-1].append(expr)
            elif token in ['AND', 'OR']:
                stack[-1].append(token)
            else:
                stack[-1].append(token)

        def build_tree(expr):
            if isinstance(expr, list):
                if len(expr) == 1:
                    return build_tree(expr[0])
                elif 'OR' in expr:
                    idx = expr.index('OR')
                    return Node('operator', 'OR', build_tree(expr[:idx]), build_tree(expr[idx + 1:]))
                elif 'AND' in expr:
                    idx = expr.index('AND')
                    return Node('operator', 'AND', build_tree(expr[:idx]), build_tree(expr[idx + 1:]))
            return Node('operand', ' '.join(expr))

        return build_tree(stack[0])

    return parse_expression()


# Evaluate the AST against user data
def evaluate_ast(ast, data):
    if ast.type == 'operator':
        if ast.value == 'AND':
            return evaluate_ast(ast.left, data) and evaluate_ast(ast.right, data)
        elif ast.value == 'OR':
            return evaluate_ast(ast.left, data) or evaluate_ast(ast.right, data)
    elif ast.type == 'operand':
        left, op, right = ast.value.split()
        left_value = data.get(left)
        right_value = int(right) if right.isdigit() else right.strip("'")
        if op == '>':
            return left_value > right_value
        elif op == '<':
            return left_value < right_value
        elif op == '=':
            return left_value == right_value
    return False


# Create a new rule
@app.route('/create_rule', methods=['POST'])
def create_rule():
    rule_string = request.json['rule_string']
    try:
        ast = parse_rule_string(rule_string)
        rule = {
            "rule_string": rule_string,
            "ast": json.dumps(ast.to_dict())
        }
        result = rules_collection.insert_one(rule)
        return jsonify({'id': str(result.inserted_id), 'ast': rule['ast']})
    except Exception as e:
        logging.error(f"Error creating rule: {e}")
        return jsonify({'error': 'Failed to create rule'}), 500


# Combine existing rules into a new rule
@app.route('/combine_rules', methods=['POST'])
def combine_rules():
    rule_ids = request.json['rule_ids']
    try:
        rules = rules_collection.find({"_id": {"$in": [ObjectId(id) for id in rule_ids]}})

        combined_ast = Node('operator', 'AND', *[Node.from_dict(json.loads(rule['ast'])) for rule in rules])
        combined_rule_string = " AND ".join([rule['rule_string'] for rule in rules])

        combined_rule = {
            "rule_string": combined_rule_string,
            "ast": json.dumps(combined_ast.to_dict())
        }
        result = rules_collection.insert_one(combined_rule)
        return jsonify({'id': str(result.inserted_id), 'combined_ast': json.dumps(combined_ast.to_dict())})
    except Exception as e:
        logging.error(f"Error combining rules: {e}")
        return jsonify({'error': 'Failed to combine rules'}), 500


# Evaluate a rule against given data
@app.route('/evaluate_rule', methods=['POST'])
def evaluate_rule():
    rule_id = request.json['rule_id']
    data = request.json['data']
    try:
        rule = rules_collection.find_one({"_id": ObjectId(rule_id)})
        if not rule:
            return jsonify({'error': 'Rule not found'}), 404
        ast = Node.from_dict(json.loads(rule['ast']))
        result = evaluate_ast(ast, data)
        return jsonify({'result': result})
    except Exception as e:
        logging.error(f"Error evaluating rule: {e}")
        return jsonify({'error': 'Failed to evaluate rule'}), 500


# Modify an existing rule
@app.route('/modify_rule', methods=['POST'])
def modify_rule():
    rule_id = request.json['rule_id']
    new_rule_string = request.json['new_rule_string']
    try:
        ast = parse_rule_string(new_rule_string)
        result = rules_collection.update_one(
            {"_id": ObjectId(rule_id)},
            {"$set": {"rule_string": new_rule_string, "ast": json.dumps(ast.to_dict())}}
        )

        if result.matched_count > 0:
            return jsonify({'message': 'Rule updated successfully'})
        else:
            return jsonify({'message': 'Rule not found'}), 404
    except Exception as e:
        logging.error(f"Error modifying rule: {e}")
        return jsonify({'error': 'Failed to modify rule'}), 500


if __name__ == '__main__':
    app.run(debug=False)





# mongodb+srv://new-user:OGcenXO5y7QMM10o@atulast.kg8pz.mongodb.net/ruleEngine?retryWrites=true&w=majority
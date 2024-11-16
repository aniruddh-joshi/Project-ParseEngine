import streamlit as st
import requests
import json
from flask import Flask, request, jsonify
from pymongo import MongoClient
from bson import ObjectId
import logging

# --- MongoDB Configuration ---
client = MongoClient('mongodb+srv://new-user:OGcenXO5y7QMM10o@atulast.kg8pz.mongodb.net/ruleEngine?retryWrites=true&w=majority')
db = client.ruleEngine
rules_collection = db.rules

# --- Flask App Configuration ---
app = Flask(__name__)

# --- Logging Configuration ---
logging.basicConfig(level=logging.DEBUG)

# --- Define AST Node Class ---
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

# --- AST Parsing Functions ---
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

# --- Flask API Routes ---
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
        if result.matched_count == 0:
            return jsonify({'error': 'Rule not found'}), 404
        return jsonify({'success': True})
    except Exception as e:
        logging.error(f"Error modifying rule: {e}")
        return jsonify({'error': 'Failed to modify rule'}), 500

# --- Streamlit Frontend ---
BASE_URL = "http://127.0.0.1:5000"

# Toggle theme function
def toggle_theme():
    st.session_state.dark_mode = not st.session_state.dark_mode

# Set up session state for dark mode
if "dark_mode" not in st.session_state:
    st.session_state.dark_mode = False

# CSS styling for themes, headers, and content
dark_mode_css = """
<style>
    /* Dark theme styles */
    body, .stApp {
        background-color: #333 !important;
        color: #f5f5f5;
    }
    .block-container {
        padding-top: 1rem;
    }
    .header {
        font-size: 3.25rem;
        font-weight: bold;
        text-align: center;
        color: #76c7c0;
        margin-bottom: 0.5rem;
        text-shadow: 2px 2px 4px #888888;
    }
    .header .emoji {
        font-size: 2rem;
        vertical-align: middle;
    }
    .subheader {
        color: #76c7c0;
        font-size: 1.5rem;
        text-align: center;
        margin: 5px 0;
    }
    .rule-section {
        background-color: #444;
        padding: 20px;
        border-radius: 10px;
        box-shadow: 2px 2px 10px rgba(0, 0, 0, 0.2);
        color: #f5f5f5;
    }
    h2, h3, h4 {
        color: #f5f5f5;
    }
    /* Button styling for visibility in both themes */
    .stButton>button {
        background-color: #ff4b4b !important;
        color: white !important;
        border: none;
        border-radius: 8px;
        padding: 0.5rem 1rem;
        font-weight: bold;
    }
    /* Small text color adjustment for dark theme */
    .small-text {
        color: #cccccc !important;
        font-size: 2rem;
    }
</style>
"""

light_mode_css = """
<style>
    /* Light theme styles */
    body, .stApp {
        background-color: #f4f4f4 !important;
        color: #000000;
    }
    .block-container {
        padding-top: 1rem;
    }
    .header {
        font-size: 3.25rem;
        font-weight: bold;
        text-align: center;
        color: #007BFF;
        margin-bottom: 0.5rem;
        text-shadow: 2px 2px 4px #888888;
    }
    .header .emoji {
        font-size: 2rem;
        vertical-align: middle;
    }
    .subheader {
        color: #007BFF;
        font-size: 1.5rem;
        text-align: center;
        margin: 5px 0;
    }
    .rule-section {
        background-color: #f0f0f0;
        padding: 20px;
        border-radius: 10px;
        box-shadow: 2px 2px 10px rgba(0, 0, 0, 0.1);
    }
    h2, h3, h4 {
        color: #000000;
    }
    /* Button styling for visibility in both themes */
    .stButton>button {
        background-color: #ff4b4b !important;
        color: white !important;
        border: none;
        border-radius: 8px;
        padding: 0.5rem 1rem;
        font-weight: bold;
    }
    /* Small text styling for light theme */
    .small-text {
        color: #555 !important;
        font-size: 2rem;
    }
</style>
"""

# Load CSS based on theme
if st.session_state.dark_mode:
    st.markdown(dark_mode_css, unsafe_allow_html=True)
else:
    st.markdown(light_mode_css, unsafe_allow_html=True)

# Project Header and Theme Toggle
st.markdown("<div class='header'>🚀 Project: AST Rule Engine</div>", unsafe_allow_html=True)
st.markdown("<div class='subheader'>Developed by: Aniruddh Joshi and Diksha Bargali</div>", unsafe_allow_html=True)
if st.button("🌙 Toggle Dark Mode" if not st.session_state.dark_mode else "☀️ Toggle Light Mode"):
    toggle_theme()
    st.experimental_rerun()

# Introduction Sections
st.markdown("<div class='rule-section'>", unsafe_allow_html=True)
st.markdown("<h2>💡 Project Overview</h2>", unsafe_allow_html=True)
st.write("This Rule Engine application provides a user-friendly platform for creating, combining, evaluating, and modifying rules.")
st.markdown("<h2>🛠️ How We Built It</h2>", unsafe_allow_html=True)
st.write("We used Python with Flask as the backend and Streamlit as the frontend, making it highly interactive and accessible.")
st.markdown("<h2>🎯 Purpose</h2>", unsafe_allow_html=True)
st.write("This project is designed to simplify rule management, enhancing productivity and decision-making across various applications.")
st.markdown("</div>", unsafe_allow_html=True)

# Toggle for Rule Engine Interface
if "show_rule_engine" not in st.session_state:
    st.session_state.show_rule_engine = False

if st.button("🔧 Open Rule Engine" if not st.session_state.show_rule_engine else "❌ Close Rule Engine"):
    st.session_state.show_rule_engine = not st.session_state.show_rule_engine
    st.experimental_rerun()

# Functions for Rule Engine Operations
def create_rule(rule_string):
    try:
        response = requests.post(f"{BASE_URL}/create_rule", json={"rule_string": rule_string})
        response.raise_for_status()
        st.success(f"Rule Created Successfully: {response.json()}", icon="✅")
    except requests.exceptions.RequestException as e:
        st.error(f"Error: {e}", icon="🚫")

def combine_rules(rule_ids):
    rule_ids = [id.strip() for id in rule_ids.split(',')]
    try:
        response = requests.post(f"{BASE_URL}/combine_rules", json={"rule_ids": rule_ids})
        response.raise_for_status()
        st.success(f"Rules Combined Successfully: {response.json()}", icon="🔗")
    except requests.exceptions.RequestException as e:
        st.error(f"Error: {e}", icon="🚫")

def evaluate_rule(mega_rule_id, data):
    try:
        data_json = json.loads(data)
        response = requests.post(f"{BASE_URL}/evaluate_rule", json={"rule_id": mega_rule_id, "data": data_json})
        response.raise_for_status()
        st.success(f"Rule Evaluation Result: {response.json()}", icon="🔍")
    except json.JSONDecodeError as e:
        st.error(f"Invalid JSON Format: {e}", icon="⚠️")
    except requests.exceptions.RequestException as e:
        st.error(f"Error: {e}", icon="🚫")

def modify_rule(rule_id, new_rule_string):
    try:
        response = requests.post(f"{BASE_URL}/modify_rule", json={"rule_id": rule_id, "new_rule_string": new_rule_string})
        response.raise_for_status()
        st.success(f"Rule Modified Successfully: {response.json()}", icon="✏️")
    except requests.exceptions.RequestException as e:
        st.error(f"Error: {e}", icon="🚫")

# Rule Engine Interface
if st.session_state.show_rule_engine:
    st.header("🔧 Rule Engine Interface")
    st.markdown("<div class='rule-section'>", unsafe_allow_html=True)

    # Create Rule Section
    st.subheader("📝 Create a New Rule")
    rule_string = st.text_input("Enter Rule Expression", placeholder="Example: (age > 18) AND (income > 5000)")
    if st.button("Create Rule"):
        create_rule(rule_string)

    st.markdown("<hr/>", unsafe_allow_html=True)

    # Combine Rules Section
    st.subheader("🔗 Combine Existing Rules")
    rule_ids = st.text_input("Combine Rules by IDs", placeholder="Example: 123, 456")
    if st.button("Combine Rules"):
        combine_rules(rule_ids)

    st.markdown("<hr/>", unsafe_allow_html=True)

    # Evaluate Rule Section
    st.subheader("🔍 Evaluate Rule")
    mega_rule_id = st.text_input("Enter Rule ID")
    data = st.text_area("Data (JSON format)", placeholder='{"age": 30, "income": 7000}')
    if st.button("Evaluate Rule"):
        evaluate_rule(mega_rule_id, data)

    st.markdown("<hr/>", unsafe_allow_html=True)

    # Modify Rule Section
    st.subheader("✏️ Modify an Existing Rule")
    modify_rule_id = st.text_input("Enter Rule ID to Modify")
    new_rule_string = st.text_input("New Rule Expression", placeholder="Example: (age > 20) OR (income > 5000)")
    if st.button("Modify Rule"):
        modify_rule(modify_rule_id, new_rule_string)

    st.markdown("</div>", unsafe_allow_html=True)

# Example of small text with visibility adjustments
st.markdown("<p class='small-text'>Note: Make sure your rules are well-defined to avoid logical errors.</p>", unsafe_allow_html=True)

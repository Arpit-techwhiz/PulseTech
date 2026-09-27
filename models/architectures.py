import tensorflow as tf
from tensorflow.keras import layers, models
import numpy as np

# ═══════════════════════════════════════════════════════════════
#  PulseTech Model Architectures — v4 Final Year Edition
#  Includes: ResNet, CNN-BiLSTM, CNN-BiLSTM-Attention (original)
#            + PulseTech-v4: Multi-Scale CNN + SE + Transformer
# ═══════════════════════════════════════════════════════════════

# ─── SHARED BUILDING BLOCKS ───────────────────────────────────

def squeeze_excitation_block(x, ratio=8):
    """
    Squeeze-and-Excitation block for channel-wise feature recalibration.
    Learns to weight important ECG frequency channels adaptively.
    """
    channels = x.shape[-1]
    se = layers.GlobalAveragePooling1D()(x)
    se = layers.Dense(max(1, channels // ratio), activation='relu')(se)
    se = layers.Dense(channels, activation='sigmoid')(se)
    se = layers.Reshape((1, channels))(se)
    return layers.Multiply()([x, se])


def transformer_encoder_block(x, num_heads=4, ff_dim=128, dropout=0.1):
    """
    A single Transformer encoder block with:
    - Multi-head self-attention
    - Feed-forward sublayer
    - Pre-LayerNorm (more stable than post-LayerNorm)
    - Residual connections
    """
    d_model = x.shape[-1]

    # Pre-norm self-attention
    attn_in = layers.LayerNormalization(epsilon=1e-6)(x)
    attn_out = layers.MultiHeadAttention(
        num_heads=num_heads,
        key_dim=max(1, d_model // num_heads),
        dropout=dropout
    )(attn_in, attn_in)
    attn_out = layers.Dropout(dropout)(attn_out)
    x = layers.Add()([x, attn_out])

    # Pre-norm feed-forward
    ff_in = layers.LayerNormalization(epsilon=1e-6)(x)
    ff = layers.Dense(ff_dim, activation='gelu')(ff_in)
    ff = layers.Dropout(dropout)(ff)
    ff = layers.Dense(d_model)(ff)
    ff = layers.Dropout(dropout)(ff)
    x = layers.Add()([x, ff])

    return x


def positional_encoding(seq_len, d_model):
    """
    Learnable positional encoding for Transformer.
    """
    positions = tf.range(start=0, limit=seq_len, delta=1)
    return layers.Embedding(input_dim=seq_len, output_dim=d_model)(positions)


# ─── ORIGINAL ARCHITECTURES (unchanged) ───────────────────────

def build_hybrid_resnet(ecg_shape=(90, 1), vitals_shape=(29,), num_classes=10):
    """
    Hybrid 1D ResNet + Dense Vitals Branch for multi-label classification.
    """
    ecg_input = layers.Input(shape=ecg_shape, name="ecg_input")
    vitals_input = layers.Input(shape=vitals_shape, name="vitals_input")

    # ECG Branch: ResNet
    x = layers.Conv1D(32, kernel_size=5, strides=1, padding='same')(ecg_input)
    x = layers.BatchNormalization()(x)
    x = layers.ReLU()(x)

    shortcut = layers.Conv1D(64, kernel_size=1, strides=1, padding='same')(x)
    shortcut = layers.BatchNormalization()(shortcut)

    x1 = layers.Conv1D(64, kernel_size=5, strides=1, padding='same')(x)
    x1 = layers.BatchNormalization()(x1)
    x1 = layers.ReLU()(x1)
    x1 = layers.Conv1D(64, kernel_size=5, strides=1, padding='same')(x1)
    x1 = layers.BatchNormalization()(x1)

    x = layers.add([shortcut, x1])
    x = layers.ReLU()(x)
    x = layers.MaxPool1D(pool_size=2)(x)

    ecg_feat = layers.GlobalAveragePooling1D()(x)
    ecg_feat = layers.Dense(64, activation='relu')(ecg_feat)

    # Vitals Branch: Dense
    v = layers.Dense(64, activation='relu')(vitals_input)
    v = layers.BatchNormalization()(v)
    v = layers.ReLU()(v)
    vitals_feat = layers.Dense(32, activation='relu')(v)

    # Fusion
    merged = layers.concatenate([ecg_feat, vitals_feat])
    f = layers.Dense(64, activation='relu')(merged)
    f = layers.Dropout(0.3)(f)
    f = layers.Dense(32, activation='relu')(f)

    outputs = layers.Dense(num_classes, activation='sigmoid', name="output")(f)

    model = models.Model(inputs=[ecg_input, vitals_input], outputs=outputs, name="Hybrid_ResNet")
    return model


def build_hybrid_cnn_bilstm(ecg_shape=(90, 1), vitals_shape=(29,), num_classes=10):
    """
    Hybrid 1D CNN + BiLSTM + Dense Vitals Branch.
    """
    ecg_input = layers.Input(shape=ecg_shape, name="ecg_input")
    vitals_input = layers.Input(shape=vitals_shape, name="vitals_input")

    # ECG Branch: CNN + BiLSTM
    x = layers.Conv1D(64, kernel_size=5, activation='relu', padding='same')(ecg_input)
    x = layers.BatchNormalization()(x)
    x = layers.MaxPool1D(pool_size=2)(x)

    x = layers.Conv1D(128, kernel_size=5, activation='relu', padding='same')(x)
    x = layers.BatchNormalization()(x)
    x = layers.MaxPool1D(pool_size=2)(x)

    ecg_feat = layers.Bidirectional(layers.LSTM(64, return_sequences=False, unroll=True))(x)

    # Vitals Branch: Dense
    v = layers.Dense(64, activation='relu')(vitals_input)
    v = layers.BatchNormalization()(v)
    v = layers.ReLU()(v)
    vitals_feat = layers.Dense(32, activation='relu')(v)

    # Fusion
    merged = layers.concatenate([ecg_feat, vitals_feat])
    f = layers.Dense(64, activation='relu')(merged)
    f = layers.Dropout(0.3)(f)
    f = layers.Dense(32, activation='relu')(f)

    outputs = layers.Dense(num_classes, activation='sigmoid', name="output")(f)

    model = models.Model(inputs=[ecg_input, vitals_input], outputs=outputs, name="Hybrid_CNN_BiLSTM")
    return model


def build_hybrid_attention(ecg_shape=(90, 1), vitals_shape=(29,), num_classes=10):
    """
    Hybrid ECG Branch (CNN -> BiLSTM -> Attention) fused with Vitals Branch (Dense)
    into a Multi-Label Output (Sigmoid).
    """
    ecg_input = layers.Input(shape=ecg_shape, name="ecg_input")
    vitals_input = layers.Input(shape=vitals_shape, name="vitals_input")

    # ECG Branch: CNN -> BiLSTM -> Attention
    x = layers.Conv1D(64, kernel_size=5, activation='relu', padding='same')(ecg_input)
    x = layers.BatchNormalization()(x)
    x = layers.MaxPool1D(pool_size=2)(x)

    x = layers.Conv1D(128, kernel_size=5, activation='relu', padding='same')(x)
    x = layers.BatchNormalization()(x)
    x = layers.MaxPool1D(pool_size=2)(x)

    # BiLSTM outputting sequence for Attention
    lstm_out = layers.Bidirectional(layers.LSTM(64, return_sequences=True, unroll=True))(x)

    # Self-Attention
    attn_out = layers.MultiHeadAttention(num_heads=4, key_dim=32)(lstm_out, lstm_out)
    attn_out = layers.Dropout(0.2)(attn_out)

    # Residual and Layer Normalization
    x = layers.LayerNormalization(epsilon=1e-6)(lstm_out + attn_out)

    # Pooling
    ecg_feat = layers.GlobalAveragePooling1D()(x)

    # Vitals Branch: Dense
    v = layers.Dense(64, activation='relu')(vitals_input)
    v = layers.BatchNormalization()(v)
    v = layers.ReLU()(v)
    vitals_feat = layers.Dense(32, activation='relu')(v)

    # Fusion
    merged = layers.concatenate([ecg_feat, vitals_feat])
    f = layers.Dense(64, activation='relu')(merged)
    f = layers.Dropout(0.3)(f)
    f = layers.Dense(32, activation='relu')(f)

    outputs = layers.Dense(num_classes, activation='sigmoid', name="output")(f)

    model = models.Model(inputs=[ecg_input, vitals_input], outputs=outputs, name="Hybrid_CNN_BiLSTM_Attention")
    return model


# ─── NEW: PULSETECH-v4 ─────────────────────────────────────────

def build_pulsetech_v4(ecg_shape=(90, 1), vitals_shape=(29,), num_classes=10,
                       d_model=128, num_transformer_layers=2,
                       num_heads=4, ff_dim=256, dropout=0.15):
    """
    PulseTech-v4: Final Year Project Flagship Architecture.

    ECG Branch:
      - Multi-scale parallel CNN (kernels 3, 7, 15) → captures P, QRS, T-wave morphology
      - Squeeze-and-Excitation recalibration → adaptive channel weighting
      - Projection → Transformer Encoder (2 layers) → temporal modelling
      - CLS-token global representation

    Vitals Branch:
      - 3-layer deep MLP with residual connections and LayerNorm
      - Handles 29 handcrafted + demographic features

    Cross-Modal Fusion:
      - ECG attends to vitals (cross-attention) → multi-modal alignment
      - Concatenation → shared classification head
      - Per-class sigmoid output for multi-label prediction

    Parameters
    ----------
    ecg_shape   : (seq_len, channels) — default (90, 1)
    vitals_shape: (feature_dim,) — default (29,)
    num_classes : number of ECG condition labels — default 10
    d_model     : transformer model dimension
    num_transformer_layers : depth of transformer encoder
    num_heads   : attention heads
    ff_dim      : feed-forward hidden dim in transformer
    dropout     : dropout rate throughout model
    """
    ecg_input    = layers.Input(shape=ecg_shape,    name="ecg_input")
    vitals_input = layers.Input(shape=vitals_shape, name="vitals_input")

    # ── ECG BRANCH ─────────────────────────────────────────────

    # 1. Multi-scale feature extraction (parallel convolutions)
    branch_short = layers.Conv1D(32, kernel_size=3,  padding='same', activation='gelu')(ecg_input)
    branch_mid   = layers.Conv1D(32, kernel_size=7,  padding='same', activation='gelu')(ecg_input)
    branch_long  = layers.Conv1D(32, kernel_size=15, padding='same', activation='gelu')(ecg_input)

    # Concatenate all scales → rich multi-resolution features
    x = layers.Concatenate(axis=-1)([branch_short, branch_mid, branch_long])  # (90, 96)
    x = layers.BatchNormalization()(x)

    # 2. Deep CNN stack with Squeeze-Excitation
    x = layers.Conv1D(64, kernel_size=5, padding='same', activation='gelu')(x)
    x = layers.BatchNormalization()(x)
    x = squeeze_excitation_block(x, ratio=8)
    x = layers.MaxPool1D(pool_size=2)(x)    # (45, 64)
    x = layers.Dropout(dropout / 2)(x)

    x = layers.Conv1D(d_model, kernel_size=3, padding='same', activation='gelu')(x)
    x = layers.BatchNormalization()(x)
    x = squeeze_excitation_block(x, ratio=8)
    x = layers.MaxPool1D(pool_size=3)(x)    # (15, d_model)
    x = layers.Dropout(dropout / 2)(x)

    # 3. Positional encoding (learnable)
    seq_len = x.shape[1]  # 15
    positions = tf.range(start=0, limit=seq_len, delta=1)
    pos_embed = layers.Embedding(input_dim=seq_len, output_dim=d_model)(positions)  # (15, d_model)
    pos_embed = tf.expand_dims(pos_embed, axis=0)  # (1, 15, d_model)
    x = layers.Add()([x, pos_embed])

    # 4. Transformer Encoder (stacked)
    for _ in range(num_transformer_layers):
        x = transformer_encoder_block(x, num_heads=num_heads, ff_dim=ff_dim, dropout=dropout)

    # ── VITALS BRANCH (Deep MLP with Residual) ─────────────────
    v = layers.Dense(128, activation='gelu')(vitals_input)
    v = layers.LayerNormalization(epsilon=1e-6)(v)
    v = layers.Dropout(dropout)(v)

    v_res = v
    v = layers.Dense(128, activation='gelu')(v)
    v = layers.LayerNormalization(epsilon=1e-6)(v)
    v = layers.Add()([v, v_res])   # residual

    v = layers.Dense(64, activation='gelu')(v)
    v = layers.LayerNormalization(epsilon=1e-6)(v)
    vitals_feat = layers.Dropout(dropout)(v)

    # ── CROSS-MODAL ATTENTION FUSION ───────────────────────────
    # Repeat vitals vector across 15 temporal steps to form Key/Value (15, d_model) for ECG Query (15, d_model)
    vitals_tiled = layers.RepeatVector(15)(vitals_feat)          # (15, 64)
    vitals_proj  = layers.Dense(d_model, activation='gelu')(vitals_tiled)  # (15, d_model)

    # ECG sequence attends to vitals across all 15 time steps
    cross_attn = layers.MultiHeadAttention(
        num_heads=num_heads, key_dim=d_model // num_heads, dropout=dropout
    )(query=x, key=vitals_proj, value=vitals_proj)
    
    x_fused = layers.Add()([x, cross_attn])
    x_fused = layers.LayerNormalization(epsilon=1e-6)(x_fused)

    # 5. Global average + max pooling → richer representation
    ecg_avg = layers.GlobalAveragePooling1D()(x_fused)   # (d_model,)
    ecg_max = layers.GlobalMaxPooling1D()(x_fused)       # (d_model,)
    ecg_feat = layers.Concatenate()([ecg_avg, ecg_max])  # (2*d_model,)
    ecg_feat = layers.Dense(d_model, activation='gelu')(ecg_feat)
    ecg_feat = layers.LayerNormalization(epsilon=1e-6)(ecg_feat)

    # ── CLASSIFICATION HEAD ────────────────────────────────────
    merged = layers.Concatenate()([ecg_feat, vitals_feat])

    f = layers.Dense(256, activation='gelu')(merged)
    f = layers.LayerNormalization(epsilon=1e-6)(f)
    f = layers.Dropout(dropout)(f)

    f = layers.Dense(128, activation='gelu')(f)
    f = layers.LayerNormalization(epsilon=1e-6)(f)
    f = layers.Dropout(dropout)(f)

    f = layers.Dense(64, activation='gelu')(f)
    f = layers.Dropout(dropout / 2)(f)

    # Multi-label sigmoid output
    outputs = layers.Dense(num_classes, activation='sigmoid', name="output")(f)

    model = models.Model(
        inputs=[ecg_input, vitals_input],
        outputs=outputs,
        name="PulseTech_v4"
    )
    return model


if __name__ == "__main__":
    # Validate all architectures
    for name, fn, kwargs in [
        ("ResNet",                 build_hybrid_resnet,    {}),
        ("CNN_BiLSTM",             build_hybrid_cnn_bilstm, {}),
        ("CNN_BiLSTM_Attention",   build_hybrid_attention,  {}),
        ("PulseTech_v4",           build_pulsetech_v4,      {}),
    ]:
        m = fn(**kwargs)
        print(f"\n{'='*60}")
        print(f"Model: {name}  |  Params: {m.count_params():,}")
        m.summary(line_length=90)

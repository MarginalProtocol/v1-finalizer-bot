import click
import os
from typing import Annotated  # NOTE: Only Python 3.9+

from ape import Contract
from ape.exceptions import TransactionError
from ape.types import ContractLog

from ape_ethereum import multicall
from ape_aws.accounts import KmsAccount

from taskiq import Context, TaskiqDepends, TaskiqState

from silverback import AppState, SilverbackApp


# Do this to initialize your app
app = SilverbackApp()


# Supplier, pool, and receiver contracts
supplier = Contract(os.environ["CONTRACT_ADDRESS_MARGV1LB_SUPPLIER"])
pool = Contract(os.environ["CONTRACT_ADDRESS_MARGV1LB_POOL"])
# @dev assumes is of type MarginalV1LBLiquidityReceiver.sol
receiver = Contract(supplier.receivers(pool.address))
margv1_factory = Contract(os.environ["CONTRACT_ADDRESS_MARGV1_FACTORY"])

# Whether to execute transaction through private mempool
TXN_PRIVATE = os.environ.get("TXN_PRIVATE", "False") == "True"

# Required confirmations to wait for transaction to go through
TXN_REQUIRED_CONFIRMATIONS = os.environ.get("TXN_REQUIRED_CONFIRMATIONS", 1)

# Whether to ask to enable autosign for local account
PROMPT_AUTOSIGN = app.signer and not isinstance(app.signer, KmsAccount)


@app.on_startup()
def app_startup(startup_state: AppState):
    # set up autosign if desired
    if PROMPT_AUTOSIGN and click.confirm("Enable autosign?"):
        app.signer.set_autosign(enabled=True)

    return {
        "message": "Starting...",
        "block_number": startup_state.last_block_seen,
    }


# Can handle some initialization on startup, like models or network connections
@app.on_worker_startup()
def worker_startup(state: TaskiqState):
    state.block_count = 0
    state.signer_balance = app.signer.balance

    state.token0 = pool.token0()
    state.token1 = pool.token1()
    state.tick_lower = pool.tickLower()
    state.tick_upper = pool.tickUpper()
    state.timestamp_initialize = pool.blockTimestampInitialize()
    state.sqrt_price_initialize_x96 = pool.sqrtPriceInitializeX96()
    state.sqrt_price_finalize_x96 = pool.sqrtPriceFinalizeX96()

    state.observation_cardinality_minimum = (
        margv1_factory.observationCardinalityMinimum()
    )

    # TODO: state.db = MyDB() if allow for tracking many pools
    return {"message": "Worker started."}


# Finalizes pool and mints uniswap v3 liquidity via receiver
def finalize_and_mint_univ3_liquidity(context: Annotated[Context, TaskiqDepends()]):
    # TODO: retry logic
    txn = multicall.Transaction()

    # finalize
    fargs = (
        context.state.token0,
        context.state.token1,
        context.state.tick_lower,
        context.state.tick_upper,
        context.state.timestamp_initialize,
    )
    txn.add(supplier.finalize, *fargs, allowFailure=False)

    # mint uniswap v3
    txn.add(receiver.mintUniswapV3, allowFailure=False)

    # preview before sending in case of revert
    try:
        click.echo("Submitting multicall pool finalize ...")
        txn(
            sender=app.signer,
            required_confirmations=TXN_REQUIRED_CONFIRMATIONS,
            private=TXN_PRIVATE,
        )
    except TransactionError as err:
        # didn't finalize and mint uniswap v3 liquidity
        click.secho(
            f"Transaction error on pool finalize: {err}",
            blink=True,
            bold=True,
        )


# This is how we trigger off of events
# Set new_block_timeout to adjust the expected block time.
@app.on_(pool.Swap)
def exec_pool_swap(log: ContractLog, context: Annotated[Context, TaskiqDepends()]):
    click.echo(f"Swap occurred with event: {log}")
    if log.finalized:
        click.echo("Finalizing pool and minting liquidity on Uniswap v3 ...")
        finalize_and_mint_univ3_liquidity(context=context)

    return {
        "finalized": log.finalized,
        "sqrt_price_x96": log.sqrtPriceX96,
        "sqrt_price_initialize_x96": context.state.sqrt_price_initialize_x96,
        "sqrt_price_finalize_x96": context.state.sqrt_price_finalize_x96,
    }


# This is how we trigger off of events
# Set new_block_timeout to adjust the expected block time.
@app.on_(receiver.MintUniswapV3)
def exec_receiver_mint_univ3(
    log: ContractLog, context: Annotated[Context, TaskiqDepends()]
):
    click.echo(f"Mint uniswap v3 occurred with event: {log}")
    # initialize the oracle if needed
    univ3_pool = Contract(log.uniswapV3Pool)
    slot0 = univ3_pool.slot0()

    if slot0.observationCardinalityNext < context.state.observation_cardinality_minimum:
        # preview before sending in case of revert
        try:
            click.echo("Submitting oracle increase observation cardinality ...")
            univ3_pool.increaseObservationCardinalityNext(
                context.state.observation_cardinality_minimum,
                sender=app.signer,
                required_confirmations=TXN_REQUIRED_CONFIRMATIONS,
                private=TXN_PRIVATE,
            )
        except TransactionError as err:
            # didn't increase observation cardinality on oracle
            click.secho(
                f"Transaction error on oracle increase observation cardinality: {err}",
                blink=True,
                bold=True,
            )

    return {
        "univ3_pool": log.uniswapV3Pool,
        "token_id": log.tokenId,
        "liquidity": log.liquidity,
    }


# Just in case you need to release some resources or something
@app.on_worker_shutdown()
def worker_shutdown(state):
    return {
        "message": f"Worker stopped after handling {state.block_count} blocks.",
        "block_count": state.block_count,
    }


# A final job to execute on Silverback shutdown
@app.on_shutdown()
def app_shutdown():
    return {"message": "Stopping..."}
